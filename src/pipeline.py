"""
Scraping pipeline: scrape → validate → compare → alert → store.

Key engineering features:
  - Circuit breaker protection (skip sites that are repeatedly failing)
  - Retry with exponential backoff via tenacity
  - Alert spam prevention (24-hour cooldown)
  - Graceful degradation (single product failure doesn't abort the run)
"""
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from circuit_breaker import CircuitBreaker
from database import Database
from models import PriceSnapshot, AlertConfig, StockStatus
from notifications import send_email_alert, send_slack_alert
from scrapers.registry import get_scraper_for_url

# Module-level circuit breaker shared across all pipeline calls in a run
circuit_breaker = CircuitBreaker()

# Module-level database instance (initialised by main.py; tests can override)
db: Optional[Database] = None


def init_db(database: Database) -> None:
    """Inject the database instance (called by main.py at startup)."""
    global db
    db = database


# ------------------------------------------------------------------
# Alert logic
# ------------------------------------------------------------------

def should_alert(
    new_snapshot: PriceSnapshot,
    last_snapshot: Optional[PriceSnapshot],
    config: Optional[AlertConfig],
) -> tuple[bool, str]:
    """
    Determine whether an alert should be sent for a price/stock change.

    Spam prevention:
      - No alerts within 24 hours of the last alert sent
      - Only triggers on meaningful price drops (>= threshold_percent)
      - Stock alerts only fire for back-in-stock events (not going out)

    Returns:
        (should_send: bool, reason: str)
    """
    if last_snapshot is None:
        return False, "First scrape - no comparison available"

    if config is None:
        return False, "No alert config for this product"

    # 24-hour cooldown window
    if config.last_alert_sent:
        cooldown = datetime.now() - config.last_alert_sent
        if cooldown < timedelta(hours=24):
            remaining = 24 - cooldown.total_seconds() / 3600
            logger.debug(
                f"Alert suppressed — in cooldown ({remaining:.1f}h remaining)"
            )
            return False, "Cooldown active"

    # Price drop threshold check
    if new_snapshot.price < last_snapshot.price and last_snapshot.price > 0:
        percent_drop = (
            (last_snapshot.price - new_snapshot.price) / last_snapshot.price * 100
        )
        if percent_drop >= config.threshold_percent:
            return True, f"Price dropped {percent_drop:.1f}%"

    # Back-in-stock check (only alert when coming BACK into stock)
    if config.alert_on_stock_change:
        was_unavailable = last_snapshot.stock_status != StockStatus.IN_STOCK
        now_available = new_snapshot.stock_status == StockStatus.IN_STOCK
        if was_unavailable and now_available:
            return True, "Back in stock"

    return False, "No significant change"


# ------------------------------------------------------------------
# Scraping with retry
# ------------------------------------------------------------------

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
async def scrape_with_retry(scraper, url: str) -> Optional[PriceSnapshot]:
    """Wrap a scraper call with exponential-backoff retry (3 attempts)."""
    return await scraper.scrape(url)


# ------------------------------------------------------------------
# Main pipeline
# ------------------------------------------------------------------

async def run_scrape_pipeline(product_id: int, url: str, site: str) -> None:
    """
    End-to-end pipeline for a single product:
        scrape → validate → compare → alert → store

    Failures are caught and logged; they do NOT propagate so the caller
    (main.py gather loop) can continue with other products.
    """
    assert db is not None, "Database not initialised — call init_db() first"

    logger.info(
        "Starting scrape pipeline",
        product_id=product_id,
        site=site,
    )

    # Check circuit breaker before attempting the scrape
    if circuit_breaker.is_open(site):
        logger.warning(
            f"Circuit breaker open for {site}, skipping product_id={product_id}"
        )
        return

    try:
        # 1. Scrape with retry logic
        scraper_class = get_scraper_for_url(url)
        scraper = scraper_class()
        raw_data = await scrape_with_retry(scraper, url)

        if not raw_data:
            logger.warning("No data returned", product_id=product_id, url=url)
            circuit_breaker.record_failure(site)
            return

        circuit_breaker.record_success(site)

        # 2. Build validated snapshot (Pydantic enforces types here)
        new_snapshot = PriceSnapshot(
            product_id=product_id,
            price=raw_data.price,
            currency=raw_data.currency,
            stock_status=raw_data.stock_status,
        )
        logger.info(
            "Validated snapshot",
            product_id=product_id,
            price=new_snapshot.price,
            stock=new_snapshot.stock_status.value,
        )

        # 3. Retrieve last snapshot and alert config
        last_snapshot = db.get_last_snapshot(product_id)
        alert_config = db.get_alert_config(product_id)

        # 4. Decide whether to alert
        should_send, reason = should_alert(new_snapshot, last_snapshot, alert_config)

        if should_send:
            logger.info(f"Alert triggered: {reason}", product_id=product_id)
            product = db.get_product(product_id)

            if last_snapshot and product and last_snapshot.price > 0:
                percent_drop = (
                    (last_snapshot.price - new_snapshot.price) / last_snapshot.price * 100
                )

                try:
                    send_email_alert(
                        product.name,
                        last_snapshot.price,
                        new_snapshot.price,
                        percent_drop,
                        str(product.url),
                    )
                except Exception as e:
                    logger.error(f"Email notification failed: {e}")

                try:
                    send_slack_alert(
                        product.name,
                        last_snapshot.price,
                        new_snapshot.price,
                        percent_drop,
                        str(product.url),
                        site,
                    )
                except Exception as e:
                    logger.error(f"Slack notification failed: {e}")

            db.update_last_alert(product_id)
        else:
            logger.debug(f"No alert needed: {reason}", product_id=product_id)

        # 5. Store snapshot (idempotency handled inside insert_snapshot)
        snapshot_id = db.insert_snapshot(new_snapshot)
        if snapshot_id:
            logger.success(
                "Pipeline completed",
                product_id=product_id,
                snapshot_id=snapshot_id,
            )
        else:
            logger.debug("Duplicate snapshot skipped", product_id=product_id)

    except Exception as e:
        logger.error(
            "Pipeline failed",
            product_id=product_id,
            site=site,
            error=str(e),
            exc_info=True,
        )
        circuit_breaker.record_failure(site)
        # Don't re-raise: let the main loop continue with other products


# ------------------------------------------------------------------
# Cross-site best deals
# ------------------------------------------------------------------

def get_best_deals() -> List[Dict[str, Any]]:
    """
    Find the lowest in-stock price across sites for each tracked product.

    Note: Currently matches by exact (lowercased) name equality.
    For production with real inventory, use fuzzy matching (e.g. RapidFuzz)
    to handle minor naming variations across retailers.
    """
    assert db is not None, "Database not initialised — call init_db() first"

    products = db.get_all_active_products()
    product_groups: Dict[str, list] = {}

    for product in products:
        key = product.name.lower().strip()
        product_groups.setdefault(key, []).append(product)

    best_deals = []

    for product_name, variants in product_groups.items():
        if len(variants) < 2:
            continue  # Only interesting if tracked on multiple sites

        prices = []
        for variant in variants:
            latest = db.get_last_snapshot(variant.id)
            if latest and latest.stock_status == StockStatus.IN_STOCK:
                prices.append(
                    {
                        "site": variant.site,
                        "price": latest.price,
                        "url": str(variant.url),
                        "product_id": variant.id,
                    }
                )

        if len(prices) >= 2:
            sorted_prices = sorted(prices, key=lambda x: x["price"])
            best = sorted_prices[0]
            worst = sorted_prices[-1]

            best_deals.append(
                {
                    "product_name": product_name,
                    "best_site": best["site"],
                    "best_price": best["price"],
                    "best_url": best["url"],
                    "worst_price": worst["price"],
                    "savings": worst["price"] - best["price"],
                    "savings_percent": (
                        (worst["price"] - best["price"]) / worst["price"] * 100
                    ),
                    "all_prices": sorted_prices,
                }
            )

    return sorted(best_deals, key=lambda x: x["savings"], reverse=True)
