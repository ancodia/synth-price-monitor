"""
Juno Records scraper (www.juno.co.uk) - minimal stub.

TODO: Implement the three extraction methods following the same pattern as
      thomann.py / gear4music.py:
        1. Inspect a Juno product page in DevTools to find the CSS selectors
        2. Fill in _extract_price, _extract_stock, _extract_name
        3. Remove the NotImplementedError raises
"""
from playwright.async_api import Page

from models import StockStatus
from .base import SiteScraper


class JunoScraper(SiteScraper):
    """Scraper for Juno Records product pages (stub — requires implementation)."""

    site_name = "juno"

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
