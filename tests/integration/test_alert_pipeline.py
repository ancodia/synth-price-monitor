"""
Integration tests for the full alert pipeline.

Tests the decision -> send notifications -> verify flow using inline
PriceSnapshot objects (no database required).
"""

from models import PriceSnapshot, StockStatus, AlertConfig
from notifications import send_slack_alert, send_email_alert
from pipeline import should_alert

from .mock_services import MockSlackServer, MockSMTPServer


class TestFullAlertPipeline:
    """
    Integration test: price drop -> should_alert -> send notifications -> verify.
    """

    def test_full_alert_flow(
        self,
        mock_slack: MockSlackServer,
        mock_smtp: MockSMTPServer,
        notification_env,
    ):
        """End-to-end: price drop triggers both Slack and email with correct content."""
        mock_slack.clear()
        mock_smtp.clear()

        old = PriceSnapshot(
            product_id=1,
            price=549.00,
            currency="GBP",
            stock_status=StockStatus.IN_STOCK,
        )
        new = PriceSnapshot(
            product_id=1,
            price=499.00,
            currency="GBP",
            stock_status=StockStatus.IN_STOCK,
        )

        config = AlertConfig(
            product_id=1,
            threshold_percent=5.0,
            alert_on_stock_change=True,
            last_alert_sent=None,
        )
        should_send, reason = should_alert(new, old, config)
        assert should_send is True

        send_slack_alert(
            product_name="Roland TR-8S",
            old_price=549.00,
            new_price=499.00,
            percent_drop=9.1,
            product_url="https://www.thomann.co.uk/roland_tr_8s.htm",
            site="thomann",
        )
        send_email_alert(
            product_name="Roland TR-8S",
            old_price=549.00,
            new_price=499.00,
            percent_drop=9.1,
            product_url="https://www.thomann.co.uk/roland_tr_8s.htm",
        )

        assert len(mock_slack.messages) == 1
        slack_msg = mock_slack.messages[0]
        assert slack_msg.header_text == "Price Alert"
        assert slack_msg.contains_text("Roland TR-8S")
        assert slack_msg.contains_text("499.00")
        assert slack_msg.contains_text("549.00")
        assert slack_msg.contains_text("Thomann")

        assert len(mock_smtp.emails) == 1
        email = mock_smtp.emails[0]
        assert "Roland TR-8S" in email.subject
        assert email.contains_text("499.00")
        assert email.contains_text("549.00")

    def test_no_alert_when_price_stable(
        self,
        mock_slack: MockSlackServer,
        mock_smtp: MockSMTPServer,
        notification_env,
    ):
        """When price hasn't changed meaningfully, no notifications should be sent."""
        mock_slack.clear()
        mock_smtp.clear()

        old = PriceSnapshot(
            product_id=1,
            price=559.00,
            currency="GBP",
            stock_status=StockStatus.IN_STOCK,
        )
        new = PriceSnapshot(
            product_id=1,
            price=558.50,
            currency="GBP",
            stock_status=StockStatus.IN_STOCK,
        )
        config = AlertConfig(
            product_id=1,
            threshold_percent=5.0,
            alert_on_stock_change=True,
            last_alert_sent=None,
        )

        should_send, _ = should_alert(new, old, config)
        assert should_send is False
        assert len(mock_slack.messages) == 0
        assert len(mock_smtp.emails) == 0
