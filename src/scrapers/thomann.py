"""
Thomann scraper (www.thomann.co.uk).
"""

from playwright.async_api import Page, expect

from models import StockStatus
from .base import SiteScraper


class ThomannScraper(SiteScraper):
    """Scraper for Thomann product pages."""

    site_name = "thomann"

    async def _handle_cookie_consent(self, page):
        try:
            accept_button = page.locator("button.js-accept-all-cookies")
            await accept_button.wait_for(state="visible", timeout=5000)
            await accept_button.click()
            await expect(accept_button).to_be_hidden()
        except Exception:
            # Cookie prompt didn't appear, continue
            pass

    async def _extract_price(self, page: Page) -> str:
        selector = ".price.fx-text"
        element = await page.wait_for_selector(selector, timeout=10_000)
        return await element.inner_text()

    async def _extract_stock(self, page: Page) -> StockStatus:
        selector = ".fx-availability"
        try:
            element = await page.query_selector(selector)
            if element is None:
                return StockStatus.OUT_OF_STOCK
            text = (await element.inner_text()).lower()
            if "available" in text or "in stock" in text:
                return StockStatus.IN_STOCK
            if "low stock" in text or "only" in text:
                return StockStatus.LOW_STOCK
            return StockStatus.OUT_OF_STOCK
        except Exception:
            return StockStatus.OUT_OF_STOCK

    async def _extract_name(self, page: Page) -> str:
        selector = ".product-title h1"
        element = await page.wait_for_selector(selector, timeout=10_000)
        return (await element.inner_text()).strip()
