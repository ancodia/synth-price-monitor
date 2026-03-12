"""
Gear4Music scraper (www.gear4music.com).
"""

from playwright.async_api import Page, expect

from models import StockStatus
from .base import SiteScraper


class Gear4MusicScraper(SiteScraper):
    """Scraper for Gear4Music product pages."""

    site_name = "gear4music"

    async def _handle_cookie_consent(self, page):
        try:
            accept_button = page.locator("button#banner-cookie-consent-eu-allow-all")
            await accept_button.wait_for(state="visible", timeout=5000)
            await accept_button.click()
            await expect(accept_button).to_be_hidden()
        except Exception:
            # Cookie prompt didn't appear, continue
            pass

    async def _extract_price(self, page: Page) -> str:
        selector = ".info-row-pricing .c-val"
        element = await page.wait_for_selector(selector, timeout=10_000)
        return await element.inner_text()

    async def _extract_stock(self, page: Page) -> StockStatus:
        selector = ".info-row-stock-msg"
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
        selector = ".pdp-title h1"
        element = await page.wait_for_selector(selector, timeout=10_000)
        return (await element.inner_text()).strip()
