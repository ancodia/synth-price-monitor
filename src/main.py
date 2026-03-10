"""
Main entry point for scheduled scraping runs.

Invoked by:
  - GitHub Actions (daily cron at 6am UTC)
  - docker-compose --profile manual run --rm scraper
  - python src/main.py  (local testing)

Exits with code 1 if ALL products failed (signals CI failure).
"""
import asyncio
import sys

from loguru import logger

from database import Database
from pipeline import run_scrape_pipeline, init_db


def configure_logging() -> None:
    """Set up stdout + rotating file logging."""
    logger.remove()  # Remove default handler
    logger.add(
        sys.stdout,
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {message}",
    )
    logger.add(
        "logs/scraper_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        rotation="00:00",        # New file each day
        retention="30 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {message} | {extra}",
    )


async def main() -> None:
    """Run the scraping pipeline for all active products."""
    configure_logging()

    logger.info("=" * 60)
    logger.info("Starting scheduled scrape run")
    logger.info("=" * 60)

    database = Database("price_monitor.db")
    init_db(database)

    products = database.get_all_active_products()
    logger.info(f"Found {len(products)} active products to scrape")

    if not products:
        logger.warning("No products configured — nothing to scrape")
        return

    # Rate limit: max 3 concurrent browser instances
    semaphore = asyncio.Semaphore(3)
    success_count = 0
    failure_count = 0

    async def scrape_with_limit(product):
        nonlocal success_count, failure_count
        async with semaphore:
            try:
                await run_scrape_pipeline(
                    product.id, str(product.url), product.site
                )
                success_count += 1
            except Exception as e:
                logger.error(f"Unhandled error for product_id={product.id}: {e}")
                failure_count += 1
            finally:
                # Polite delay between scrapes (be a good citizen)
                await asyncio.sleep(2)

    await asyncio.gather(*[scrape_with_limit(p) for p in products])

    logger.info("=" * 60)
    logger.success(
        f"Scrape run complete: {success_count} succeeded, {failure_count} failed"
    )
    logger.info("=" * 60)

    # Signal CI failure only if everything failed
    if failure_count > 0 and success_count == 0:
        logger.error("All scrapes failed!")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
