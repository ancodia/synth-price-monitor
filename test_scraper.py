"""Quick scraper test - no database required"""
import asyncio
import sys
sys.path.insert(0, 'src')

from src.scrapers.registry import get_scraper_for_url

async def test_url(url: str):
    print(f"Testing scraper for: {url}")
    print("-" * 60)
    
    scraper_class = get_scraper_for_url(url)
    scraper = scraper_class()
    
    result = await scraper.scrape(url)
    
    if result:
        print(f"✅ Success!")
        print(f"Name: {result.name}")
        print(f"Price: £{result.price:.2f}")
        print(f"Stock: {result.stock_status.value}")
        print(f"Site: {result.site}")
    else:
        print("❌ Scraping failed")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_scraper.py <product_url>")
        sys.exit(1)
    
    asyncio.run(test_url(sys.argv[1]))