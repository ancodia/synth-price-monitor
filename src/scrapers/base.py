"""
Abstract base class for all site scrapers.

Each retailer scraper inherits from SiteScraper and implements `scrape()`.
Common price-parsing logic lives here so it's tested once and reused everywhere.
"""
import re
from abc import ABC, abstractmethod
from typing import Optional

from models import ScrapedProduct


class SiteScraper(ABC):
    """Abstract base class for product page scrapers."""

    @abstractmethod
    async def scrape(self, url: str) -> Optional[ScrapedProduct]:
        """
        Scrape a single product page and return structured data.

        Args:
            url: Full product page URL

        Returns:
            ScrapedProduct if extraction succeeded, None otherwise
        """
        ...

    def _parse_price(self, text: str) -> float:
        """
        Parse a price string into a float.

        Handles formats:
            £589.00   → 589.0
            £589      → 589.0
            £589 inc. VAT → 589.0
            589,00 €  → 589.0   (European decimal comma)
            1,299.00  → 1299.0  (thousands separator)

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
