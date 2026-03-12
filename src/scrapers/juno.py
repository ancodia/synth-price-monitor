"""
Juno Records scraper (www.juno.co.uk) - minimal stub.
"""

from playwright.async_api import Page, expect

from models import StockStatus
from .base import SiteScraper


class JunoScraper(SiteScraper):
    """Scraper for Juno Records product pages (stub — requires implementation)."""

    site_name = "juno"

    async def _handle_cookie_consent(self, page):
        try:
            accept_button = page.locator("#juno-cookie-consent button")
            await accept_button.wait_for(state="visible", timeout=5000)
            await accept_button.click()
            await expect(accept_button).to_be_hidden()
        except Exception:
            # Cookie prompt didn't appear, continue
            pass

    async def _extract_price(self, page: Page) -> str:
        selector = ".product-pricing-eq h2"
        element = await page.wait_for_selector(selector, timeout=10_000)
        return await element.inner_text()

    async def _extract_stock(self, page: Page) -> StockStatus:
        selector = "#product-instock"
        try:
            element = await page.query_selector(selector)
            if element is None:
                return StockStatus.OUT_OF_STOCK
            text = (await element.inner_text()).lower()
            if "in stock" in text or "available" in text:
                return StockStatus.IN_STOCK
            if "low stock" in text or "limited" in text:
                return StockStatus.LOW_STOCK
            return StockStatus.OUT_OF_STOCK
        except Exception:
            return StockStatus.OUT_OF_STOCK

    async def _extract_name(self, page: Page) -> str:
        selector = ".product-title-eq h1"
        element = await page.wait_for_selector(selector, timeout=10_000)
        return (await element.inner_text()).strip()
