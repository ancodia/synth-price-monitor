"""
Shared fixtures for e2e tests.

Manages:
  - Fresh SQLite database per test session
  - Mock Slack webhook server
  - Mock SMTP server
  - Streamlit dashboard process (started once, used by all UI tests)
  - Environment variable injection for notification credentials
"""

import base64
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

from database import Database
from pipeline import init_db

from .mock_services import MockSlackServer, MockSMTPServer
from .seed_test_data import seed_full_scenario

# Resolve project root (two levels up from tests/e2e/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------

SLACK_PORT = 9100
SMTP_PORT = 9025
STREAMLIT_PORT = 8599  # Non-default port to avoid clashes
STREAMLIT_STARTUP_TIMEOUT = 30  # seconds


# ------------------------------------------------------------------
# Database fixtures
# ------------------------------------------------------------------


@pytest.fixture(scope="session")
def test_db_path(tmp_path_factory):
    """Create a temporary DB path shared across the entire test session."""
    tmp_dir = tmp_path_factory.mktemp("e2e_data")
    db_path = str(tmp_dir / "test_price_monitor.db")
    yield db_path


@pytest.fixture(scope="session")
def db(test_db_path):
    """Session-scoped database, initialised once and shared across all tests."""
    database = Database(test_db_path)
    init_db(database)
    yield database
    database.close()


@pytest.fixture(scope="session")
def seeded_db(db):
    """
    Database pre-loaded with Roland TR-8S across 3 retailers + price history + a price drop.

    Returns the seed scenario dict containing product_ids and drop details.
    """
    scenario = seed_full_scenario(db)
    return scenario


# ------------------------------------------------------------------
# Mock notification servers
# ------------------------------------------------------------------


@pytest.fixture(scope="session")
def mock_slack():
    """Session-scoped mock Slack webhook server."""
    server = MockSlackServer(port=SLACK_PORT)
    server.start()
    time.sleep(0.2)
    yield server
    server.stop()


@pytest.fixture(scope="session")
def mock_smtp():
    """Session-scoped mock SMTP server."""
    server = MockSMTPServer(port=SMTP_PORT)
    server.start()
    time.sleep(0.2)
    yield server
    server.stop()


@pytest.fixture(scope="session")
def notification_env(mock_slack, mock_smtp):
    """
    Set environment variables so the pipeline sends notifications
    to our mock servers instead of real Slack/email.
    """
    env = {
        "SLACK_WEBHOOK_URL": mock_slack.webhook_url,
        "SMTP_HOST": "127.0.0.1",
        "SMTP_PORT": str(SMTP_PORT),
        "SMTP_USER": "test@example.com",
        "SMTP_PASSWORD": "testpassword",
        "EMAIL_FROM": "test@example.com",
        "EMAIL_TO": "recipient@example.com",
        "SMTP_USE_TLS": "false",  # Plain SMTP for mock server
    }

    original_env = {}
    for key, value in env.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value

    yield env

    # Restore original environment
    for key, original in original_env.items():
        if original is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = original


# ------------------------------------------------------------------
# Streamlit dashboard process
# ------------------------------------------------------------------


@pytest.fixture(scope="session")
def streamlit_app(test_db_path, seeded_db, notification_env):
    """
    Start the Streamlit dashboard as a subprocess, wait for it to be ready,
    and yield the base URL. Kills the process on teardown.

    The dashboard is pointed at the test database by copying it to the
    project root where app.py expects to find price_monitor.db.
    """
    project_db_path = PROJECT_ROOT / "price_monitor.db"
    backup_path = None

    if project_db_path.exists():
        backup_path = PROJECT_ROOT / "price_monitor.db.e2e_backup"
        shutil.copy2(project_db_path, backup_path)

    # Copy test DB to where the dashboard expects it
    shutil.copy2(test_db_path, project_db_path)

    # Start Streamlit
    env = {**os.environ, "STREAMLIT_SERVER_PORT": str(STREAMLIT_PORT)}
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(PROJECT_ROOT / "dashboard" / "app.py"),
            "--server.port",
            str(STREAMLIT_PORT),
            "--server.address",
            "127.0.0.1",
            "--server.headless",
            "true",
            "--browser.gatherUsageStats",
            "false",
        ],
        env=env,
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for Streamlit to become responsive
    base_url = f"http://127.0.0.1:{STREAMLIT_PORT}"
    _wait_for_server(base_url, timeout=STREAMLIT_STARTUP_TIMEOUT)

    yield base_url

    # Teardown: kill Streamlit
    process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()

    # Restore original DB if we backed it up
    if backup_path and backup_path.exists():
        shutil.copy2(backup_path, project_db_path)
        backup_path.unlink()
    elif project_db_path.exists():
        project_db_path.unlink()


def _wait_for_server(url: str, timeout: int = 30):
    """Poll a URL until it responds or timeout is reached."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                return
        except requests.ConnectionError:
            pass
        time.sleep(1)
    raise TimeoutError(f"Streamlit did not start within {timeout}s at {url}")


# ------------------------------------------------------------------
# Playwright fixtures (using pytest-playwright)
# ------------------------------------------------------------------


@pytest.fixture(scope="session")
def browser_context_args():
    """Configure Playwright browser context for tests."""
    return {
        "viewport": {"width": 1280, "height": 900},
        "ignore_https_errors": True,
    }


# @pytest.fixture(scope="session")
# def browser_type_launch_args():
#     return {
#         "headless": False,
#     }


# ------------------------------------------------------------------
# Screenshot capture for HTML report
# ------------------------------------------------------------------


try:
    from pytest_html import extras as html_extras

    _PYTEST_HTML = True
except ImportError:
    _PYTEST_HTML = False


def _png_extra(screenshot_bytes: bytes):
    """Convert raw screenshot bytes to a pytest-html PNG extra (v4 requires base64 string)."""
    return html_extras.png(base64.b64encode(screenshot_bytes).decode("utf-8"))


@pytest.fixture
def attach_screenshot(request):
    """Attach element-level screenshots to the pytest-html report for a test."""

    def _attach(screenshot_bytes: bytes):
        if not hasattr(request.node, "_element_screenshots"):
            request.node._element_screenshots = []
        request.node._element_screenshots.append(screenshot_bytes)

    return _attach


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    if not _PYTEST_HTML:
        return
    report = outcome.get_result()
    if report.when != "call":
        return

    extra = getattr(report, "extras", [])

    # Element screenshots attached explicitly during the test
    for screenshot in getattr(item, "_element_screenshots", []):
        extra.append(_png_extra(screenshot))

    # Full-page screenshot for visual context (every UI test)
    page = item.funcargs.get("page")
    if page is not None:
        try:
            extra.append(_png_extra(page.screenshot(full_page=False)))
        except Exception:
            pass

    report.extras = extra
