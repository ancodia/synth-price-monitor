"""
Synchronous wrapper for the async Playwright scrapers.

Streamlit runs its own event loop which conflicts with asyncio.run().
This module creates a fresh event loop per call to safely bridge the gap.

Usage:
    from scraper_sync import scrape_product_sync
    result = scrape_product_sync("https://www.thomann.co.uk/...")
"""
import asyncio
import sys
import os
from typing import Optional

# Make src/ importable from dashboard/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from scrapers.registry import get_scraper_for_url
from models import ScrapedProduct


def scrape_product_sync(url: str) -> Optional[ScrapedProduct]:
    """
    Synchronous wrapper around the async scraper.

    Creates a new event loop for this call and closes it afterwards,
    preventing conflicts with any existing loop (e.g. Streamlit's own).

    Args:
        url: Product page URL from a supported retailer

    Returns:
        ScrapedProduct if successful, None on failure (error shown via st.error)
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            scraper_class = get_scraper_for_url(url)
            scraper = scraper_class()
            result = loop.run_until_complete(scraper.scrape(url))
            return result
        finally:
            loop.close()

    except Exception as e:
        import streamlit as st
        st.error(f"Scraping failed: {e}")
        return None
