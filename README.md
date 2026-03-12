# UK Synth Price Monitor

[![Unit Tests](https://github.com/ancodia/synth-price-monitor/actions/workflows/unit-tests.yml/badge.svg)](https://github.com/ancodia/synth-price-monitor/actions/workflows/unit-tests.yml)
[![E2E Tests](https://github.com/ancodia/synth-price-monitor/actions/workflows/e2e-tests.yml/badge.svg)](https://github.com/ancodia/synth-price-monitor/actions/workflows/e2e-tests.yml)
[![Test Report](https://img.shields.io/badge/Test%20Report-GitHub%20Pages-blue)](https://ancodia.github.io/synth-price-monitor/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview

Multi-site price monitoring system that tracks synthesizer prices across UK retailers (Thomann, Gear4Music, Juno Records), with intelligent alerting via Slack and email when prices drop or products come back in stock.

**Key Differentiators**:
- Production-grade data validation (Pydantic at every boundary)
- Circuit breaker pattern for resilient scraping
- Idempotency protection against duplicate data
- Performance monitoring and structured logging
- Smart alerting with threshold-based triggers and spam prevention
- Fully automated via GitHub Actions
- **User-controlled product grouping** — manual naming with autocomplete for multi-site comparison
- **Combined price charts** — visual comparison of all retailers on a single chart
- **Inline alert configuration** — adjust settings directly in the comparison table

## Architecture

```mermaid
graph TB
    A[Streamlit Dashboard] -->|Add Products| B[SQLite Database]
    C[Playwright Scrapers] -->|Extract Data| D[Pydantic Validation]
    D -->|Price Snapshots| E[Pipeline Orchestration]
    E -->|Idempotency Check| B
    E -->|Detect Changes| F[Alert Logic]
    F -->|Price Drop/Stock Change| G[Slack Webhook]
    F -->|Price Drop/Stock Change| H[Email SMTP]
    I[GitHub Actions] -->|Schedule Daily| C
    J[Circuit Breaker] -->|Protect| C
    B -->|Historical Data| K[Plotly Charts]
    K -->|Visualize| A

    style E fill:#90EE90
    style F fill:#FFB6C1
    style J fill:#FFD700
```

## Features

### Core Functionality
- **Multi-site scraping**: Monitors Thomann, Gear4Music, Juno Records
- **User-controlled grouping**: Name products manually, autocomplete suggests existing names
- **Price history**: 30-day trend tracking with visualisation
- **Combined charts**: Multi-site products show all retailers on a single chart for easy comparison
- **Inline alert settings**: Configure thresholds and stock alerts directly in the comparison table
- **Smart alerts**: Configurable threshold-based notifications (default: 5% drop)
- **Slack integration**: Rich Block Kit messages with direct product links
- **Email notifications**: HTML alerts with savings calculations
- **Web dashboard**: Add/manage products via Streamlit UI with automatic refresh
- **Automated scraping**: Daily GitHub Actions runs with zero infrastructure cost
- **Smart reactivation**: Re-adding deleted products restores them with full price history

### Production Engineering Features
- **Idempotency Protection**: Prevents duplicate price snapshots when data hasn't changed
- **Circuit Breaker**: Automatically skips failing sites for 1 hour after 3 consecutive failures
- **Alert Spam Prevention**: 24-hour cooldown windows prevent notification fatigue
- **Performance Monitoring**: Every scrape logs duration for performance tracking
- **Structured Logging**: Full observability with contextual logs (product_id, site, errors)
- **Graceful Degradation**: Single product failures don't crash the entire pipeline
- **Retry Logic**: Exponential backoff (3 attempts) for transient failures
- **Soft Delete**: Products can be reactivated with full price history intact

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Git
- (Optional) Slack workspace for notifications

### Local Development

1. **Clone repository**
   ```bash
   git clone https://github.com/ancodia/synth-price-monitor.git
   cd synth-price-monitor
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your SMTP and Slack credentials
   ```

3. **Generate sample data** (optional — populates the DB for demo)
   ```bash
   uv sync
   uv run python scripts/generate_sample_data.py
   ```

4. **Start dashboard**
   ```bash
   docker-compose up dashboard
   ```

5. **Open browser** at http://localhost:8501

### Manual Scrape

```bash
docker-compose --profile manual run --rm scraper
```

### Without Docker

```bash
uv sync
uv run playwright install chromium

# Run scraper
uv run python src/main.py

# Run dashboard
uv run streamlit run dashboard/app.py
```

## Using the Dashboard

### Adding Products

The dashboard uses a manual naming system with autocomplete for reliable product grouping:

1. **First Product**:
   - Paste product URL (e.g., `https://www.thomann.co.uk/gb/roland_tr8s.htm`)
   - Select "➕ Add new product name..." from dropdown
   - Enter a name (e.g., "Roland TR-8S")
   - Click "Add Product"

2. **Same Product from Another Retailer**:
   - Paste second URL (e.g., `https://www.gear4music.com/roland-tr8s`)
   - Select "Roland TR-8S" from dropdown (autocomplete)
   - Click "Add Product"

3. **Automatic Grouping**:
   - Products with identical names are grouped together
   - Shows combined price comparison table
   - Single chart with all retailers overlaid
   - Inline alert settings per retailer

### Multi-Site Product View

When multiple retailers are tracked for the same product:

**Price Comparison Table**:
- All retailers listed with current price and stock status
- Best price highlighted with 🏆
- Alert threshold % and stock alert toggle inline
- 💾 Save button to update settings per retailer
- 🔗 Link to product page

**Combined Price Chart**:
- All retailers on a single chart (color-coded)
- Visual comparison of price trends over 30 days
- Interactive hover shows all prices simultaneously
- Identify which retailer has better pricing patterns

**Manage Retailers**:
- Delete individual retailers while keeping others
- Soft delete — re-adding restores full price history

### Single-Site Product View

Products tracked on one site get the classic layout:
- Price history chart on the left
- Alert settings panel on the right
- Delete button

### Alert Configuration

Configure per product per retailer:
- **Alert Threshold**: Percentage price drop required (default: 5%)
- **Stock Alerts**: Get notified when out-of-stock items return

### Smart Features

- **Automatic UI Refresh**: Dashboard updates immediately after adding/deleting products
- **Smart Reactivation**: Deleted products can be restored with full history by re-adding the URL
- **Duplicate Prevention**: Can't add the same URL twice while active

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
# Email (Gmail example — use an App Password)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-specific-password
EMAIL_FROM=your-email@gmail.com
EMAIL_TO=recipient@example.com

# Slack (optional)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

### Adding a New Retailer

1. Create `src/scrapers/newsite.py` inheriting from `SiteScraper`
2. Register in `src/scrapers/registry.py`:
   ```python
   SITE_REGISTRY["newsite.com"] = NewSiteScraper
   ```
3. No changes needed anywhere else in the pipeline

## Testing

The test suite has two layers: fast unit tests and full e2e tests covering the alert pipeline and live dashboard.

### Running Tests

```bash
# All tests
uv run pytest tests/ -v

# Unit tests only (fast, no I/O)
uv run pytest tests/unit/ -v

# Alert e2e tests (mock Slack + SMTP)
uv run pytest tests/e2e/test_alerts.py -v --timeout=60

# UI e2e tests (Playwright against live Streamlit)
uv run pytest tests/e2e/test_ui.py -v --timeout=120
```

Playwright browsers must be installed before running UI tests:

```bash
uv run playwright install --with-deps chromium
```

### Test Structure

```
tests/
├── unit/
│   └── test_scrapers.py      # Price parsing, idempotency, circuit breaker, alert logic
└── e2e/
    ├── conftest.py           # Session-scoped fixtures (db, mock servers, Streamlit process)
    ├── mock_services.py      # MockSlackServer and MockSMTPServer implementations
    ├── seed_test_data.py     # Roland TR-8S across 3 retailers + price drop scenario
    ├── test_alerts.py        # Alert pipeline e2e tests
    └── test_ui.py            # Playwright UI tests against the live dashboard
```

### E2E Architecture

**Mock Services** — Both notification channels are replaced with in-process servers running in background threads for the duration of the test session.

- **MockSlackServer** listens on `http://127.0.0.1:9100/webhook` and captures every POST as a `SlackMessage` object. Tests assert on the full Block Kit payload — header text, field values, and raw content — without any Slack credentials.
- **MockSMTPServer** (via `aiosmtpd`) listens on `127.0.0.1:9025` and captures emails as `CapturedEmail` objects exposing the decoded subject and body. The `notification_env` fixture injects environment variables so production code routes to the mock servers with no code changes.

**Test Database** — A temporary SQLite database is created once per session. The `seeded_db` fixture populates it with:
- Roland TR-8S tracked across Thomann, Gear4Music, and Juno Records
- 14 days of stable price history with sub-threshold noise at each retailer
- A Thomann price drop from £549 → £499 (~9.1%) seeded as two snapshots 2 hours apart

**Streamlit Process** — The `streamlit_app` fixture starts the dashboard as a subprocess on port `8599`, pointing at the test database, and waits up to 30 seconds for it to become responsive before yielding the base URL to UI tests.

### What the E2E Tests Cover

**`test_alerts.py`**:
- `TestSlackNotification` — sends a price drop alert via `send_slack_alert()` and asserts on the captured payload: header text, product name, old/new prices, savings, retailer, and URL
- `TestEmailNotification` — same for `send_email_alert()`: verifies delivery and asserts on decoded subject and body content
- `TestAlertDecisionLogic` — tests `should_alert()` with seeded scenarios: 9.1% Thomann drop fires, 2% Gear4Music drop does not, 24h cooldown suppresses repeat alerts, stock-change alert fires on out-of-stock → in-stock transition
- `TestFullAlertPipeline` — full integration: decision → Slack send → email send → both mock servers verified in a single test

**`test_ui.py`** — Playwright tests against the live Streamlit dashboard: product display, multi-site price comparison table, Plotly chart rendering, manage retailers section, and best deals panel.

### CI

Two workflows run on every push and pull request to `main`:

- **`unit-tests.yml`** — fast-feedback unit tests only (no Playwright, ~1 min). Results published as a GitHub Check.
- **`e2e-tests.yml`** — alert pipeline and UI e2e tests. Results published as a GitHub Check. On pushes to `main`, the HTML report (with embedded screenshots) is deployed to [GitHub Pages](https://ancodia.github.io/synth-price-monitor/). Playwright traces are uploaded as artifacts on failure and retained for 14 days.

### Test Dependencies

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

## Architecture Decisions

### SQLite + Git Scraping Pattern

**Current Implementation**: Price history stored in SQLite and committed via GitHub Actions.

**Tradeoffs**:
- Zero infrastructure cost
- Easy inspection of historical data via Git
- Built-in backup via Git history
- Not suitable for > ~1000 products or sub-hourly scraping

**Production Alternative**: PostgreSQL on RDS or DynamoDB for serverless, with separate storage from application logic.

*This pattern is intentional for portfolio demonstration.*

### Manual Product Naming

**Design Decision**: Users manually name products rather than auto-normalization.

**Benefits**:
- **Reliable**: No flaky regex patterns or heuristics
- **Flexible**: Group any products you want (even different models for comparison)
- **Autocomplete**: Dropdown suggests existing names to prevent typos
- **Transparent**: User controls exactly how products are grouped

**Alternative Considered**: Automatic name normalization was tested but proved unreliable across diverse product naming conventions.

### Site Registry Pattern

Scrapers are registered in a central registry rather than hardcoded detection:

```python
SITE_REGISTRY = {
    "thomann.co.uk": ThomannScraper,
    "gear4music.com": Gear4MusicScraper,
}
```

**Benefit**: Adding new sites requires only creating a scraper class and registering it — zero pipeline changes.

### Soft Delete Pattern

Products are soft-deleted (marked inactive) rather than hard-deleted.

**Benefits**:
- Preserves price history if product is re-added
- Prevents UNIQUE constraint errors on URL
- Enables "undo" by re-adding the same URL
- Historical data available for analysis

**Implementation**: Re-adding a deleted URL reactivates the product with all snapshots intact.

### Combined vs Individual Charts

**Multi-site products**: Single chart with all retailers overlaid — easier visual comparison, identify pricing patterns, less scrolling.

**Single-site products**: Individual chart with traditional focused view and alert settings in sidebar.

## Project Structure

```
synth-price-monitor/
├── .github/
│   └── workflows/
│       └── e2e-tests.yml       # CI: unit + alert + UI tests on push/PR
├── src/
│   ├── scrapers/
│   │   ├── base.py             # Abstract scraper interface + price parser
│   │   ├── registry.py         # Site registry pattern
│   │   ├── thomann.py          # Thomann implementation
│   │   ├── gear4music.py       # Gear4Music implementation
│   │   └── juno.py             # Juno implementation
│   ├── models.py               # Pydantic data models
│   ├── database.py             # SQLite operations
│   ├── notifications.py        # Slack + Email alerts
│   ├── pipeline.py             # Orchestration + alert logic
│   ├── circuit_breaker.py      # Failure protection
│   └── main.py                 # Entry point for scraping
├── dashboard/
│   ├── app.py                  # Streamlit dashboard
│   └── scraper_sync.py         # Sync wrapper (fixes Playwright + Streamlit conflict)
├── tests/
│   ├── unit/
│   │   └── test_scrapers.py    # Unit tests
│   └── e2e/
│       ├── conftest.py         # Session fixtures
│       ├── mock_services.py    # Mock Slack + SMTP servers
│       ├── seed_test_data.py   # Test data seeding
│       ├── test_alerts.py      # Alert pipeline e2e tests
│       └── test_ui.py          # Playwright UI tests
├── scripts/
│   └── generate_sample_data.py # Demo data generation
├── logs/                       # Log output directory
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── uv.lock
├── .env.example
└── README.md
```

## Monitoring & Observability

### Example Log Output

```
2024-02-14 06:00:15 | INFO     | Starting scrape pipeline | product_id=1 | site=thomann
2024-02-14 06:00:17 | INFO     | Thomann scrape completed in 1.89s
2024-02-14 06:00:17 | INFO     | Validated snapshot | product_id=1 | price=589.00 | stock=in_stock
2024-02-14 06:00:17 | INFO     | Alert triggered: Price dropped 5.2%
2024-02-14 06:00:18 | SUCCESS  | Slack notification sent for Roland TR-8S
2024-02-14 06:00:18 | SUCCESS  | Pipeline completed | product_id=1 | snapshot_id=47
```

Logs are written to `stdout` (INFO+) for GitHub Actions and to `logs/scraper_YYYY-MM-DD.log` (DEBUG+) with 30-day rotation.

## Tech Stack

- **Scraping**: Python 3.11, Playwright, playwright-stealth
- **Data**: SQLite, Pydantic v2
- **UI**: Streamlit, Plotly
- **Notifications**: smtplib, requests (Slack webhooks)
- **Automation**: GitHub Actions
- **Deployment**: Docker, docker-compose
- **Logging**: loguru
- **Resilience**: tenacity (retry), custom circuit breaker
- **Testing**: pytest, pytest-playwright, aiosmtpd

## Roadmap

- [ ] Used/B-stock tracking
- [ ] FastAPI endpoint for external integrations
- [ ] Multi-currency support (EUR, USD conversion)
- [ ] Telegram bot notifications
- [ ] Price prediction with historical trend analysis
- [ ] Export price history to CSV
- [ ] Custom alert schedules (e.g., only notify during business hours)

## Portfolio Positioning

**This is a data pipeline automation project** that uses web scraping as the extraction mechanism.

The focus is on **systems thinking**:
- How do we build pipelines that don't break when external dependencies fail?
- How do we prevent bad data from corrupting our database?
- How do we make systems observable and debuggable?
- How do we design for maintainability and extensibility?
- How do we create intuitive user experiences for complex multi-site comparisons?

The scraping is the "what", but the engineering patterns are the "why" — and what makes this portfolio-worthy.

### Key Differentiators vs. Simple Scrapers

1. **User Experience**: Manual naming with autocomplete, combined charts, inline settings
2. **Production Resilience**: Circuit breakers, idempotency, graceful degradation
3. **Data Quality**: Pydantic validation at every boundary
4. **Observability**: Structured logging, performance monitoring
5. **Smart Features**: Soft delete with reactivation, automatic UI refresh
6. **Extensibility**: Site registry pattern makes adding retailers trivial
7. **Verified Correctness**: Two-layer test suite with real mock infrastructure

## License

MIT
