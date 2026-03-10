"""
Gear4Music scraper (www.gear4music.com).

TODO: Before using, inspect the live product page and fill in the CSS selectors below.
      Open a product in DevTools → right-click price element → Copy selector.
"""
import time
from typing import Optional

from loguru import logger
from playwright.async_api import async_playwright, Page
from playwright_stealth import stealth_async

from models import ScrapedProduct, StockStatus
from .base import SiteScraper


class Gear4MusicScraper(SiteScraper):
    """Scraper for Gear4Music product pages."""

    async def scrape(self, url: str) -> Optional[ScrapedProduct]:
        """Scrape a Gear4Music product page with performance monitoring."""
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
                f"Gear4Music scrape completed in {duration:.2f}s",
                url=url,
                duration=duration,
            )

            return ScrapedProduct(
                name=name,
                price=self._parse_price(price_text),
                currency="GBP",
                stock_status=stock_status,
                url=url,
                site="gear4music",
            )

        except Exception as e:
            duration = time.perf_counter() - start_time
            logger.error(
                f"Gear4Music scrape failed after {duration:.2f}s: {e}",
                url=url,
                error=str(e),
            )
            raise

    async def _extract_price(self, page: Page) -> str:
        # TODO: fill in CSS selector for the price element
        # Example: selector = ".pdp-price"
        selector = "TODO_GEAR4MUSIC_PRICE_SELECTOR"
        element = await page.wait_for_selector(selector, timeout=10_000)
        return await element.inner_text()

    async def _extract_stock(self, page: Page) -> StockStatus:
        # TODO: fill in CSS selector for the stock/availability element
        # Then map the text to StockStatus.IN_STOCK / LOW_STOCK / OUT_OF_STOCK
        selector = "TODO_GEAR4MUSIC_STOCK_SELECTOR"
        try:
            element = await page.query_selector(selector)
            if element is None:
                return StockStatus.OUT_OF_STOCK
            text = (await element.inner_text()).lower()
            # TODO: adjust these string matches to what Gear4Music actually shows
            if "in stock" in text or "available" in text:
                return StockStatus.IN_STOCK
            if "low stock" in text or "limited" in text:
                return StockStatus.LOW_STOCK
            return StockStatus.OUT_OF_STOCK
        except Exception:
            return StockStatus.OUT_OF_STOCK

    async def _extract_name(self, page: Page) -> str:
        # TODO: fill in CSS selector for the product name/title element
        selector = "TODO_GEAR4MUSIC_NAME_SELECTOR"
        element = await page.wait_for_selector(selector, timeout=10_000)
        return (await element.inner_text()).strip()
