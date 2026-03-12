"""
Unit tests for the should_alert() decision function.

Pure function tests — no fixtures, no database, no mock servers.
"""

from datetime import datetime, timedelta

from models import PriceSnapshot, StockStatus, AlertConfig
from pipeline import should_alert


def _snap(price, stock=StockStatus.IN_STOCK):
    return PriceSnapshot(product_id=1, price=price, currency="GBP", stock_status=stock)


class TestAlertDecisionLogic:
    """Test should_alert() with realistic scenarios using hardcoded snapshots."""

    def test_price_drop_above_threshold_triggers_alert(self):
        """A 9.1% drop should trigger an alert with a 5% threshold."""
        old = _snap(549.00)
        new = _snap(499.00)
        config = AlertConfig(
            product_id=1,
            threshold_percent=5.0,
            alert_on_stock_change=True,
            last_alert_sent=None,
        )
        result, reason = should_alert(new, old, config)
        assert result is True
        assert "Price dropped" in reason

    def test_price_drop_below_threshold_no_alert(self):
        """A 2% drop should NOT trigger with a 5% threshold."""
        old = _snap(569.00)
        new = _snap(557.62)  # ~2%
        config = AlertConfig(
            product_id=1,
            threshold_percent=5.0,
            alert_on_stock_change=True,
            last_alert_sent=None,
        )
        result, _ = should_alert(new, old, config)
        assert result is False

    def test_cooldown_suppresses_alert(self):
        """An alert within the 24h cooldown window should be suppressed."""
        old = _snap(549.00)
        new = _snap(499.00)
        config = AlertConfig(
            product_id=1,
            threshold_percent=5.0,
            alert_on_stock_change=True,
            last_alert_sent=datetime.now() - timedelta(hours=2),
        )
        result, reason = should_alert(new, old, config)
        assert result is False
        assert "Cooldown" in reason

    def test_back_in_stock_triggers_alert(self):
        """A product returning to stock should trigger an alert."""
        old = _snap(559.00, stock=StockStatus.OUT_OF_STOCK)
        new = _snap(559.00, stock=StockStatus.IN_STOCK)
        config = AlertConfig(
            product_id=1,
            threshold_percent=5.0,
            alert_on_stock_change=True,
            last_alert_sent=None,
        )
        result, reason = should_alert(new, old, config)
        assert result is True
        assert "Back in stock" in reason
