"""
Abstract base class for all site scrapers.

Uses the Template Method pattern: `scrape()` handles the full browser lifecycle
(launch, stealth, navigate, close, log timing, build result) and delegates
the three site-specific extraction steps to abstract methods on subclasses.

This means:
  - Resource leaks are impossible — browser.close() is always in a finally block
  - ~60 lines of duplicated boilerplate disappear from each scraper
  - Subclasses only need to implement _extract_price, _extract_stock, _extract_name
"""
import re
import time
from abc import ABC, abstractmethod
from typing import Optional

from loguru import logger
from playwright.async_api import async_playwright, Page
from playwright_stealth import stealth_async

from models import ScrapedProduct, StockStatus


class SiteScraper(ABC):
    """Abstract base class for product page scrapers."""

    # Subclasses must set these class-level attributes
    site_name: str = ""
    currency: str = "GBP"

    async def scrape(self, url: str) -> Optional[ScrapedProduct]:
        """
        Scrape a single product page and return structured data.

        Template method — subclasses implement _extract_price, _extract_stock,
        _extract_name. Browser lifecycle and error handling live here so they
        can't be accidentally broken or omitted in individual scrapers.

        Args:
            url: Full product page URL

        Returns:
            ScrapedProduct if extraction succeeded

        Raises:
            Exception: Re-raises any scraping failure after logging
        """
        start_time = time.perf_counter()

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    page = await browser.new_page()
                    await stealth_async(page)
                    await page.goto(url, wait_until="domcontentloaded")

                    price_text = await self._extract_price(page)
                    stock_status = await self._extract_stock(page)
                    name = await self._extract_name(page)
                finally:
                    # Always close browser — even if extraction raises
                    await browser.close()

            duration = time.perf_counter() - start_time
            logger.info(
                f"{self.site_name.title()} scrape completed in {duration:.2f}s",
                url=url,
                duration=duration,
            )

            return ScrapedProduct(
                name=name,
                price=self._parse_price(price_text),
                currency=self.currency,
                stock_status=stock_status,
                url=url,
                site=self.site_name,
            )

        except Exception as e:
            duration = time.perf_counter() - start_time
            logger.error(
                f"{self.site_name.title()} scrape failed after {duration:.2f}s: {e}",
                url=url,
                error=str(e),
            )
            raise

    @abstractmethod
    async def _extract_price(self, page: Page) -> str:
        """Return the raw price string from the page (e.g. '£589.00')."""
        ...

    @abstractmethod
    async def _extract_stock(self, page: Page) -> StockStatus:
        """Return the stock status for this product."""
        ...

    @abstractmethod
    async def _extract_name(self, page: Page) -> str:
        """Return the product name/title from the page."""
        ...

    def _parse_price(self, text: str) -> float:
        """
        Parse a price string into a float.

        Handles formats:
            £589.00       → 589.0
            £589          → 589.0
            £589 inc. VAT → 589.0
            589,00 €      → 589.0   (European decimal comma)
            1,299.00      → 1299.0  (thousands separator)

        Args:
            text: Raw price string from the page

        Returns:
            Price as float

        Raises:
            ValueError: If no numeric value can be extracted
        """
        # Strip currency symbols and VAT labels
        cleaned = text.replace("£", "").replace("€", "")
        cleaned = re.sub(r"inc\.?\s*VAT|incl\.?\s*VAT", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip()

        # Handle European decimal comma (e.g., "589,00" with no period)
        if "," in cleaned and "." not in cleaned:
            cleaned = cleaned.replace(",", ".")
        else:
            # Remove thousands separators (e.g., "1,299.00" → "1299.00")
            cleaned = cleaned.replace(",", "")

        # Extract first numeric value
        match = re.search(r"\d+(\.\d+)?", cleaned)
        if not match:
            raise ValueError(f"Could not parse price from: {text!r}")

        return float(match.group())
