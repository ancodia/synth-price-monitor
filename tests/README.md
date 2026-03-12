# Testing

## Overview

The test suite is split into two layers:

- **Unit tests** (`tests/unit/test_scrapers.py`) — fast, no I/O, cover price parsing, idempotency, circuit breaker, and alert decision logic
- **E2E tests** (`tests/e2e/`) — cover the alert pipeline and dashboard UI against real mock services

The e2e focus is the alerting system, which is the component hardest to demonstrate manually. Mock Slack and SMTP servers capture real HTTP/SMTP traffic, letting tests assert on actual message content rather than mocking at the function level.

---

## Structure

```
tests/
├── unit/
│   └── test_scrapers.py      # Unit tests (price parsing, db, circuit breaker, should_alert)
└── e2e/
    ├── __init__.py
    ├── conftest.py           # Session-scoped fixtures (db, mock servers, Streamlit process)
    ├── mock_services.py      # MockSlackServer and MockSMTPServer implementations
    ├── seed_test_data.py     # Roland TR-8S across 3 retailers + price drop scenario
    ├── test_alerts.py        # Alert pipeline e2e tests
    └── test_ui.py            # Playwright UI tests against the live dashboard
```

---

## Running the Tests

### All tests

```bash
uv run pytest tests/ -v
```

### Unit tests only (fast)

```bash
uv run pytest tests/unit/ -v
```

### Alert e2e tests

```bash
uv run pytest tests/e2e/test_alerts.py -v --timeout=60
```

### UI e2e tests

```bash
uv run pytest tests/e2e/test_ui.py -v --timeout=120
```

Playwright browsers must be installed before running UI tests:

```bash
uv run playwright install --with-deps chromium
```

---

## E2E Architecture

### Mock Services

Both notification channels are replaced with in-process servers that run in background threads for the duration of the test session.

**MockSlackServer** listens on `http://127.0.0.1:9100/webhook` and captures every POST as a `SlackMessage` object. Tests can inspect the full Block Kit payload — header text, field values, and raw content — without any Slack credentials.

**MockSMTPServer** (via `aiosmtpd`) listens on `127.0.0.1:9025` and captures emails as `CapturedEmail` objects exposing subject line and body. Plain SMTP with no TLS, matching the `SMTP_USE_TLS=false` environment variable injected by the `notification_env` fixture.

The `notification_env` fixture injects the relevant environment variables so the production notification code routes to the mock servers with no code changes.

### Test Database

A temporary SQLite database is created once per session via `tmp_path_factory`. The `seeded_db` fixture populates it with:

- Roland TR-8S tracked across Thomann, Gear4Music, and Juno Records
- 14 days of stable price history at each retailer's base price (sub-threshold noise only)
- A Thomann price drop from £549 → £499 (~9.1%) seeded as two snapshots 2 hours apart

All e2e tests run against this shared database. Nothing in the test suite deletes data, so fixture ordering doesn't matter.

### Streamlit Process

The `streamlit_app` fixture starts the dashboard as a subprocess on port `8599`, pointing at the test database. It waits up to 30 seconds for the server to become responsive before yielding the base URL to UI tests. Teardown sends `SIGTERM` and restores the original `price_monitor.db` if one existed.

---

## What the E2E Tests Cover

### `test_alerts.py`

**TestSlackNotification** — sends a price drop alert directly via `send_slack_alert()` and asserts on the captured payload: header text, product name, old/new prices, savings amount, retailer name, and product URL.

**TestEmailNotification** — same for `send_email_alert()`: verifies delivery to the mock SMTP server and asserts on subject line and body content.

**TestAlertDecisionLogic** — tests `should_alert()` with seeded database scenarios:
- 9.1% Thomann drop fires above the 5% threshold
- 2% Gear4Music drop does not fire
- Alert within 24h cooldown window is suppressed
- Out-of-stock → in-stock transition fires a stock alert

**TestFullAlertPipeline** — full integration: decision → Slack send → email send → verify both mock servers captured the correct content in a single test.

### `test_ui.py`

Playwright tests against the live Streamlit dashboard running on the test database. Covers product display, the multi-site price comparison table, Plotly chart rendering, the manage retailers section, and the best deals panel.

---

## Dependencies

Test dependencies are in the `dev` group in `pyproject.toml`:

```toml
[dependency-groups]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.23.0",
    "pytest-playwright>=0.5.0",
    "pytest-timeout>=2.2.0",
    "aiosmtpd>=1.4.4",
]
```

Install with:

```bash
uv sync --frozen
```

---

## CI

Tests run on every push and pull request to `main` via `.github/workflows/e2e-tests.yml`. Unit tests run first as a fast-fail gate, followed by alert e2e tests, then UI tests. The unit test step runs `tests/unit/` and the e2e steps each target their respective file. Test logs and Playwright traces are uploaded as artifacts and retained for 14 days.