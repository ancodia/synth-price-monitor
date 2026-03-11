"""
Unit tests for the Synth Price Monitor.

Run with:
    uv run pytest tests/ -v

Live scraper tests are marked skip — they require an internet connection
and working CSS selectors on the real sites.
"""
from datetime import datetime, timedelta

import pytest

from scrapers.base import SiteScraper
from models import PriceSnapshot, StockStatus, AlertConfig
from circuit_breaker import CircuitBreaker
from pipeline import should_alert


# ------------------------------------------------------------------
# _parse_price tests
# ------------------------------------------------------------------

class ConcreteScraper(SiteScraper):
    """Minimal concrete subclass to exercise base-class methods without a browser."""
    site_name = "test"

    async def _extract_price(self, page) -> str:
        return ""

    async def _extract_stock(self, page) -> StockStatus:
        return StockStatus.IN_STOCK

    async def _extract_name(self, page) -> str:
        return ""


@pytest.fixture
def scraper():
    return ConcreteScraper()


@pytest.mark.parametrize("raw,expected", [
    ("£589.00", 589.0),
    ("£589", 589.0),
    ("£589 inc. VAT", 589.0),
    ("£589 incl. VAT", 589.0),
    ("589,00 €", 589.0),        # European decimal comma
    ("£1,299.00", 1299.0),      # Thousands separator
    ("  £ 49.99  ", 49.99),     # Whitespace
])
def test_parse_price_formats(scraper, raw, expected):
    assert scraper._parse_price(raw) == pytest.approx(expected, abs=0.01)


def test_parse_price_invalid(scraper):
    with pytest.raises(ValueError):
        scraper._parse_price("no price here")


# ------------------------------------------------------------------
# Database idempotency tests
# ------------------------------------------------------------------

@pytest.fixture
def in_memory_db():
    from database import Database
    db = Database(":memory:")
    product_id = db.add_product("Test Synth", "thomann", "https://example.com/synth")
    return db, product_id


def make_snapshot(product_id, price, stock=StockStatus.IN_STOCK):
    return PriceSnapshot(
        product_id=product_id,
        price=price,
        currency="GBP",
        stock_status=stock,
        scraped_at=datetime.now(),
    )


def test_first_snapshot_always_inserted(in_memory_db):
    db, product_id = in_memory_db
    snap = make_snapshot(product_id, 589.00)
    assert db.should_insert_snapshot(product_id, snap) is True


def test_duplicate_snapshot_rejected(in_memory_db):
    db, product_id = in_memory_db
    snap = make_snapshot(product_id, 589.00)
    db.insert_snapshot(snap)
    duplicate = make_snapshot(product_id, 589.00)
    assert db.should_insert_snapshot(product_id, duplicate) is False


def test_price_change_accepted(in_memory_db):
    db, product_id = in_memory_db
    db.insert_snapshot(make_snapshot(product_id, 589.00))
    changed = make_snapshot(product_id, 549.00)
    assert db.should_insert_snapshot(product_id, changed) is True


def test_stock_change_accepted(in_memory_db):
    db, product_id = in_memory_db
    db.insert_snapshot(make_snapshot(product_id, 589.00, StockStatus.IN_STOCK))
    out_of_stock = make_snapshot(product_id, 589.00, StockStatus.OUT_OF_STOCK)
    assert db.should_insert_snapshot(product_id, out_of_stock) is True


def test_database_context_manager():
    """Database should support the 'with' statement."""
    from database import Database
    with Database(":memory:") as db:
        pid = db.add_product("Moog Sub 37", "thomann", "https://example.com/moog")
        assert pid > 0


# ------------------------------------------------------------------
# Circuit breaker tests
# ------------------------------------------------------------------

def test_circuit_breaker_starts_closed():
    cb = CircuitBreaker(failure_threshold=3)
    assert cb.is_open("thomann") is False


def test_circuit_breaker_opens_after_threshold():
    cb = CircuitBreaker(failure_threshold=3)
    cb.record_failure("thomann")
    cb.record_failure("thomann")
    assert cb.is_open("thomann") is False
    cb.record_failure("thomann")
    assert cb.is_open("thomann") is True


def test_circuit_breaker_reset_on_success():
    cb = CircuitBreaker(failure_threshold=3)
    cb.record_failure("thomann")
    cb.record_failure("thomann")
    cb.record_failure("thomann")
    assert cb.is_open("thomann") is True
    cb.record_success("thomann")
    assert cb.is_open("thomann") is False


def test_circuit_breaker_isolated_per_site():
    cb = CircuitBreaker(failure_threshold=2)
    cb.record_failure("thomann")
    cb.record_failure("thomann")
    assert cb.is_open("thomann") is True
    assert cb.is_open("gear4music") is False


def test_circuit_breaker_timeout_resets():
    """After timeout elapses the circuit should close and reset."""
    cb = CircuitBreaker(failure_threshold=1, timeout=timedelta(hours=1))
    cb.record_failure("juno")
    assert cb.is_open("juno") is True

    # Directly backdate opened_at to simulate time passing
    cb.opened_at["juno"] = datetime.now() - timedelta(hours=2)
    assert cb.is_open("juno") is False
    # Failures and opened_at should be cleared after auto-reset
    assert "juno" not in cb.failures
    assert "juno" not in cb.opened_at


# ------------------------------------------------------------------
# should_alert tests
# ------------------------------------------------------------------

def make_config(threshold=5.0, alert_stock=True, last_alert=None):
    return AlertConfig(
        product_id=1,
        threshold_percent=threshold,
        alert_on_stock_change=alert_stock,
        last_alert_sent=last_alert,
    )


def make_snap(price, stock=StockStatus.IN_STOCK):
    return PriceSnapshot(
        product_id=1,
        price=price,
        currency="GBP",
        stock_status=stock,
        scraped_at=datetime.now(),
    )


def test_should_alert_first_scrape_no_alert():
    new = make_snap(589.00)
    result, reason = should_alert(new, None, make_config())
    assert result is False


def test_should_alert_no_config():
    old = make_snap(589.00)
    new = make_snap(500.00)
    result, reason = should_alert(new, old, None)
    assert result is False


def test_should_alert_price_drop_above_threshold():
    old = make_snap(589.00)
    new = make_snap(540.00)  # ~8.3% drop
    result, reason = should_alert(new, old, make_config(threshold=5.0))
    assert result is True
    assert "Price dropped" in reason


def test_should_alert_price_drop_below_threshold():
    old = make_snap(589.00)
    new = make_snap(580.00)  # ~1.5% drop
    result, reason = should_alert(new, old, make_config(threshold=5.0))
    assert result is False


def test_should_alert_cooldown_suppresses():
    old = make_snap(589.00)
    new = make_snap(500.00)  # big drop
    config = make_config(last_alert=datetime.now() - timedelta(hours=2))
    result, reason = should_alert(new, old, config)
    assert result is False
    assert "Cooldown" in reason


def test_should_alert_after_cooldown_expires():
    old = make_snap(589.00)
    new = make_snap(500.00)
    config = make_config(last_alert=datetime.now() - timedelta(hours=25))
    result, reason = should_alert(new, old, config)
    assert result is True


def test_should_alert_back_in_stock():
    old = make_snap(589.00, StockStatus.OUT_OF_STOCK)
    new = make_snap(589.00, StockStatus.IN_STOCK)
    result, reason = should_alert(new, old, make_config(alert_stock=True))
    assert result is True
    assert "Back in stock" in reason


def test_should_alert_out_of_stock_no_alert():
    old = make_snap(589.00, StockStatus.IN_STOCK)
    new = make_snap(589.00, StockStatus.OUT_OF_STOCK)
    result, _ = should_alert(new, old, make_config(alert_stock=True))
    assert result is False


def test_should_alert_stock_alert_disabled():
    """Back-in-stock should NOT fire when alert_on_stock_change=False."""
    old = make_snap(589.00, StockStatus.OUT_OF_STOCK)
    new = make_snap(589.00, StockStatus.IN_STOCK)
    result, _ = should_alert(new, old, make_config(alert_stock=False))
    assert result is False


def test_should_alert_price_increase_no_alert():
    """Price increases should never trigger an alert."""
    old = make_snap(500.00)
    new = make_snap(589.00)  # price went UP
    result, _ = should_alert(new, old, make_config())
    assert result is False


def test_should_alert_zero_base_price_no_crash():
    """Zero previous price should not cause a division by zero crash."""
    old = make_snap(0.0)
    new = make_snap(100.0)
    result, _ = should_alert(new, old, make_config())
    assert result is False  # price went up, no alert


# ------------------------------------------------------------------
# Live scraper stubs (skipped — require real sites + selectors)
# ------------------------------------------------------------------

@pytest.mark.skip(reason="Requires live site access and configured CSS selectors")
def test_thomann_scraper_live():
    """
    TODO: After filling in thomann.py selectors, test with a real URL:
        url = "https://www.thomann.co.uk/gb/korg_minilogue_xd.htm"
    """
    pass


@pytest.mark.skip(reason="Requires live site access and configured CSS selectors")
def test_gear4music_scraper_live():
    """
    TODO: After filling in gear4music.py selectors, test with a real URL.
    """
    pass
