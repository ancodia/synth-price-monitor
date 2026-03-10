"""
Juno Records scraper (www.juno.co.uk) - minimal stub.

TODO: Implement this scraper following the same pattern as thomann.py / gear4music.py:
  1. Inspect a Juno product page in DevTools to find the CSS selectors
  2. Fill in _extract_price, _extract_stock, _extract_name
  3. Remove the NotImplementedError raises
"""
import time
from typing import Optional

from loguru import logger
from playwright.async_api import async_playwright, Page
from playwright_stealth import stealth_async

from models import ScrapedProduct, StockStatus
from .base import SiteScraper


class JunoScraper(SiteScraper):
    """Scraper for Juno Records product pages (stub - requires implementation)."""

    async def scrape(self, url: str) -> Optional[ScrapedProduct]:
        """Scrape a Juno Records product page."""
        start_time = time.perf_counter()

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await stealth_async(page)

                await page.goto(url, wait_until="domcontentloaded")

                price_text = await self._extract_price(page)
                stock_status = await self._extract_stock(page)
                name = await self._extract_name(page)

                await browser.close()

            duration = time.perf_counter() - start_time
            logger.info(
                f"Juno scrape completed in {duration:.2f}s",
                url=url,
                duration=duration,
            )

            return ScrapedProduct(
                name=name,
                price=self._parse_price(price_text),
                currency="GBP",
                stock_status=stock_status,
                url=url,
                site="juno",
            )

        except Exception as e:
            duration = time.perf_counter() - start_time
            logger.error(
                f"Juno scrape failed after {duration:.2f}s: {e}",
                url=url,
                error=str(e),
            )
            raise

    async def _extract_price(self, page: Page) -> str:
        # TODO: fill in CSS selector for the Juno price element
        raise NotImplementedError(
            "Juno price selector not yet implemented. "
            "Inspect a Juno product page and add the CSS selector here."
        )

    async def _extract_stock(self, page: Page) -> StockStatus:
        # TODO: fill in CSS selector for the Juno stock/availability element
        raise NotImplementedError(
            "Juno stock selector not yet implemented. "
            "Inspect a Juno product page and add the CSS selector here."
        )

    async def _extract_name(self, page: Page) -> str:
        # TODO: fill in CSS selector for the Juno product name element
        raise NotImplementedError(
            "Juno name selector not yet implemented. "
            "Inspect a Juno product page and add the CSS selector here."
        )
