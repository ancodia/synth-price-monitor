"""
Shared fixtures for integration tests.

Provides:
  - Mock Slack webhook server (port 9200)
  - Mock SMTP server (port 9225)
  - Environment variable injection pointing at mock servers
"""

import os
import time

import pytest

from .mock_services import MockSlackServer, MockSMTPServer

SLACK_PORT = 9200
SMTP_PORT = 9225


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
        "SMTP_USE_TLS": "false",
    }

    original_env = {}
    for key, value in env.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value

    yield env

    for key, original in original_env.items():
        if original is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = original
