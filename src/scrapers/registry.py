"""
Site registry pattern: maps domain names to scraper classes.

Adding a new retailer requires:
  1. Create a new scraper in src/scrapers/newsite.py
  2. Import it here and add an entry to SITE_REGISTRY
  3. No changes needed anywhere else in the pipeline
"""

from typing import Type, Dict

from .base import SiteScraper
from .thomann import ThomannScraper
from .gear4music import Gear4MusicScraper
from .juno import JunoScraper


SITE_REGISTRY: Dict[str, Type[SiteScraper]] = {
    "thomann.co.uk": ThomannScraper,
    "gear4music.com": Gear4MusicScraper,
    "juno.co.uk": JunoScraper,
}


def get_scraper_for_url(url: str) -> Type[SiteScraper]:
    """
    Detect site from URL and return the appropriate scraper class.

    Args:
        url: Full product URL

    Returns:
        Scraper class (not instance) for the detected site

    Raises:
        ValueError: If no scraper is registered for the given URL
    """
    for domain, scraper_class in SITE_REGISTRY.items():
        if domain in url:
            return scraper_class
    raise ValueError(
        f"No scraper registered for URL: {url}\n"
        f"Supported sites: {', '.join(SITE_REGISTRY.keys())}"
    )
