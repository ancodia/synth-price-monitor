# UK Synth Price Monitor

**Resilient price tracking system for UK music retailers** — demonstrating production-grade automation engineering.

Built to showcase data pipeline automation, not just web scraping.

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
- **Price history**: 30-day trend tracking with visualisation
- **Smart alerts**: Configurable threshold-based notifications (default: 5% drop)
- **Slack integration**: Rich Block Kit messages with direct product links
- **Email notifications**: HTML alerts with savings calculations
- **Web dashboard**: Add/manage products via Streamlit UI
- **Automated scraping**: Daily GitHub Actions runs with zero infrastructure cost

### Production Engineering Features
- **Idempotency Protection**: Prevents duplicate price snapshots when data hasn't changed
- **Circuit Breaker**: Automatically skips failing sites for 1 hour after 3 consecutive failures
- **Alert Spam Prevention**: 24-hour cooldown windows prevent notification fatigue
- **Performance Monitoring**: Every scrape logs duration for performance tracking
- **Structured Logging**: Full observability with contextual logs (product_id, site, errors)
- **Graceful Degradation**: Single product failures don't crash the entire pipeline
- **Retry Logic**: Exponential backoff (3 attempts) for transient failures

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Git
- (Optional) Slack workspace for notifications

### Local Development

1. **Clone repository**
   ```bash
   git clone https://github.com/yourusername/synth-price-monitor.git
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

### Adding Products

1. Open dashboard at http://localhost:8501
2. Paste a product URL from a supported retailer in the sidebar
3. Click "Add Product" — the system scrapes details automatically
4. Configure alert threshold (default: 5% price drop)
5. Enable/disable stock change alerts

### Adding a New Retailer

1. Create `src/scrapers/newsite.py` inheriting from `SiteScraper`
2. Register in `src/scrapers/registry.py`:
   ```python
   SITE_REGISTRY["newsite.com"] = NewSiteScraper
   ```
3. No changes needed anywhere else in the pipeline

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

### Site Registry Pattern

Scrapers are registered in a central registry rather than hardcoded detection:

```python
SITE_REGISTRY = {
    "thomann.co.uk": ThomannScraper,
    "gear4music.com": Gear4MusicScraper,
}
```

**Benefit**: Adding new sites requires only creating a scraper class and registering it — zero pipeline changes.

### Cross-Site Product Matching

Current implementation matches products by exact name equality.

**Production Consideration**: For real inventory, use fuzzy matching (e.g., `RapidFuzz`) to handle naming variations across retailers.

## Running Tests

```bash
uv run pytest tests/ -v
```

Unit tests cover: price parsing, idempotency logic, circuit breaker state transitions, alert cooldown and threshold logic. Live scraper tests are marked skip.

## Project Structure

```
synth-price-monitor/
├── .github/
│   └── workflows/
│       └── scrape.yml          # Daily automated runs
├── src/
│   ├── scrapers/
│   │   ├── base.py             # Abstract scraper interface + price parser
│   │   ├── registry.py         # Site registry pattern
│   │   ├── thomann.py          # Thomann implementation (TODO: selectors)
│   │   ├── gear4music.py       # Gear4Music implementation (TODO: selectors)
│   │   └── juno.py             # Juno stub (TODO: implement)
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
│   └── test_scrapers.py        # Unit tests
├── scripts/
│   └── generate_sample_data.py # Demo data generation
├── logs/                       # Log output directory
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── uv.lock                     # Committed lockfile (auto-generated)
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
2024-02-14 06:00:18 | SUCCESS  | Slack notification sent for Korg Minilogue XD
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

## Roadmap

- [ ] Used/B-stock tracking
- [ ] FastAPI endpoint for external integrations
- [ ] Fuzzy product matching with RapidFuzz
- [ ] Multi-currency support (EUR, USD conversion)
- [ ] Telegram bot notifications
- [ ] Price prediction with historical trend analysis

## Portfolio Positioning

**This is a data pipeline automation project** that uses web scraping as the extraction mechanism.

The focus is on **systems thinking**:
- How do we build pipelines that don't break when external dependencies fail?
- How do we prevent bad data from corrupting our database?
- How do we make systems observable and debuggable?
- How do we design for maintainability and extensibility?

The scraping is the "what", but the engineering patterns are the "why" — and what makes this portfolio-worthy.

## License

MIT
