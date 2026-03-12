"""
e2e tests for the alert pipeline with mocked notification services.

Validates:
  - Price drops above threshold trigger Slack and email alerts
  - Alert content includes correct product name, prices, and savings
  - Stock change alerts fire correctly
  - Cooldown suppression works
  - Below-threshold drops do NOT trigger alerts

Uses mock Slack webhook and SMTP servers from conftest.py and
injects simulated price data directly into the database.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from models import PriceSnapshot, StockStatus, AlertConfig
from notifications import send_slack_alert, send_email_alert
from pipeline import should_alert

from .mock_services import MockSlackServer, MockSMTPServer


# ------------------------------------------------------------------
# Direct notification tests (unit-level with real HTTP/SMTP to mocks)
# ------------------------------------------------------------------

class TestSlackNotification:
    """Test that Slack webhook sends correctly formatted messages."""

    def test_slack_alert_sends_to_mock(self, mock_slack: MockSlackServer, notification_env):
        mock_slack.clear()
        send_slack_alert(
            product_name="Roland TR-8S",
            old_price=549.00,
            new_price=499.00,
            percent_drop=9.1,
            product_url="https://www.thomann.co.uk/roland_tr_8s.htm",
            site="thomann",
        )
        assert len(mock_slack.messages) == 1

    def test_slack_payload_has_header(self, mock_slack: MockSlackServer, notification_env):
        mock_slack.clear()
        send_slack_alert(
            product_name="Roland TR-8S",
            old_price=549.00,
            new_price=499.00,
            percent_drop=9.1,
            product_url="https://www.thomann.co.uk/roland_tr_8s.htm",
            site="thomann",
        )
        msg = mock_slack.messages[0]
        assert msg.header_text == "Price Alert"

    def test_slack_payload_contains_product_name(self, mock_slack: MockSlackServer, notification_env):
        mock_slack.clear()
        send_slack_alert(
            product_name="Roland TR-8S",
            old_price=549.00,
            new_price=499.00,
            percent_drop=9.1,
            product_url="https://www.thomann.co.uk/roland_tr_8s.htm",
            site="thomann",
        )
        assert mock_slack.messages[0].contains_text("Roland TR-8S")

    def test_slack_payload_contains_prices(self, mock_slack: MockSlackServer, notification_env):
        mock_slack.clear()
        send_slack_alert(
            product_name="Roland TR-8S",
            old_price=549.00,
            new_price=499.00,
            percent_drop=9.1,
            product_url="https://www.thomann.co.uk/roland_tr_8s.htm",
            site="thomann",
        )
        msg = mock_slack.messages[0]
        assert msg.contains_text("549.00")
        assert msg.contains_text("499.00")

    def test_slack_payload_contains_savings(self, mock_slack: MockSlackServer, notification_env):
        mock_slack.clear()
        send_slack_alert(
            product_name="Roland TR-8S",
            old_price=549.00,
            new_price=499.00,
            percent_drop=9.1,
            product_url="https://www.thomann.co.uk/roland_tr_8s.htm",
            site="thomann",
        )
        assert mock_slack.messages[0].contains_text("50.00")

    def test_slack_payload_contains_retailer(self, mock_slack: MockSlackServer, notification_env):
        mock_slack.clear()
        send_slack_alert(
            product_name="Roland TR-8S",
            old_price=549.00,
            new_price=499.00,
            percent_drop=9.1,
            product_url="https://www.thomann.co.uk/roland_tr_8s.htm",
            site="thomann",
        )
        assert mock_slack.messages[0].contains_text("Thomann")

    def test_slack_payload_contains_product_url(self, mock_slack: MockSlackServer, notification_env):
        mock_slack.clear()
        url = "https://www.thomann.co.uk/roland_tr_8s.htm"
        send_slack_alert(
            product_name="Roland TR-8S",
            old_price=549.00,
            new_price=499.00,
            percent_drop=9.1,
            product_url=url,
            site="thomann",
        )
        assert mock_slack.messages[0].contains_text(url)


class TestEmailNotification:
    """Test that email alerts send correctly via the mock SMTP server."""

    def test_email_alert_sends_to_mock(self, mock_smtp: MockSMTPServer, notification_env):
        mock_smtp.clear()
        send_email_alert(
            product_name="Roland TR-8S",
            old_price=549.00,
            new_price=499.00,
            percent_drop=9.1,
            product_url="https://www.thomann.co.uk/roland_tr_8s.htm",
        )
        assert len(mock_smtp.emails) == 1

    def test_email_subject_contains_product_name(self, mock_smtp: MockSMTPServer, notification_env):
        mock_smtp.clear()
        send_email_alert(
            product_name="Roland TR-8S",
            old_price=549.00,
            new_price=499.00,
            percent_drop=9.1,
            product_url="https://www.thomann.co.uk/roland_tr_8s.htm",
        )
        assert "Roland TR-8S" in mock_smtp.emails[0].subject

    def test_email_subject_contains_savings(self, mock_smtp: MockSMTPServer, notification_env):
        mock_smtp.clear()
        send_email_alert(
            product_name="Roland TR-8S",
            old_price=549.00,
            new_price=499.00,
            percent_drop=9.1,
            product_url="https://www.thomann.co.uk/roland_tr_8s.htm",
        )
        assert "50.00" in mock_smtp.emails[0].subject

    def test_email_body_contains_prices(self, mock_smtp: MockSMTPServer, notification_env):
        mock_smtp.clear()
        send_email_alert(
            product_name="Roland TR-8S",
            old_price=549.00,
            new_price=499.00,
            percent_drop=9.1,
            product_url="https://www.thomann.co.uk/roland_tr_8s.htm",
        )
        email = mock_smtp.emails[0]
        assert email.contains_text("549.00")
        assert email.contains_text("499.00")

    def test_email_body_contains_product_url(self, mock_smtp: MockSMTPServer, notification_env):
        mock_smtp.clear()
        url = "https://www.thomann.co.uk/roland_tr_8s.htm"
        send_email_alert(
            product_name="Roland TR-8S",
            old_price=549.00,
            new_price=499.00,
            percent_drop=9.1,
            product_url=url,
        )
        assert mock_smtp.emails[0].contains_text(url)


# ------------------------------------------------------------------
# Alert decision logic with seeded data
# ------------------------------------------------------------------

class TestAlertDecisionLogic:
    """
    Test should_alert() with realistic scenarios using the seeded database.
    """

    def test_price_drop_above_threshold_triggers_alert(self, seeded_db):
        """A 9.1% drop on Thomann should trigger an alert."""
        drop = seeded_db["drop"]
        config = AlertConfig(
            product_id=drop["product_id"],
            threshold_percent=5.0,
            alert_on_stock_change=True,
            last_alert_sent=None,
        )
        result, reason = should_alert(
            drop["new_snapshot"], drop["old_snapshot"], config
        )
        assert result is True
        assert "Price dropped" in reason

    def test_price_drop_below_threshold_no_alert(self, seeded_db):
        """A 2% drop should NOT trigger with a 5% threshold."""
        product_id = seeded_db["product_ids"]["gear4music"]
        old = PriceSnapshot(
            product_id=product_id, price=569.00,
            currency="GBP", stock_status=StockStatus.IN_STOCK,
        )
        new = PriceSnapshot(
            product_id=product_id, price=557.62,  # ~2%
            currency="GBP", stock_status=StockStatus.IN_STOCK,
        )
        config = AlertConfig(
            product_id=product_id, threshold_percent=5.0,
            alert_on_stock_change=True, last_alert_sent=None,
        )
        result, _ = should_alert(new, old, config)
        assert result is False

    def test_cooldown_suppresses_alert(self, seeded_db):
        """An alert within the 24h cooldown window should be suppressed."""
        drop = seeded_db["drop"]
        config = AlertConfig(
            product_id=drop["product_id"],
            threshold_percent=5.0,
            alert_on_stock_change=True,
            last_alert_sent=datetime.now() - timedelta(hours=2),
        )
        result, reason = should_alert(
            drop["new_snapshot"], drop["old_snapshot"], config
        )
        assert result is False
        assert "Cooldown" in reason

    def test_back_in_stock_triggers_alert(self, seeded_db):
        """A product returning to stock should trigger an alert."""
        product_id = seeded_db["product_ids"]["juno"]
        old = PriceSnapshot(
            product_id=product_id, price=559.00,
            currency="GBP", stock_status=StockStatus.OUT_OF_STOCK,
        )
        new = PriceSnapshot(
            product_id=product_id, price=559.00,
            currency="GBP", stock_status=StockStatus.IN_STOCK,
        )
        config = AlertConfig(
            product_id=product_id, threshold_percent=5.0,
            alert_on_stock_change=True, last_alert_sent=None,
        )
        result, reason = should_alert(new, old, config)
        assert result is True
        assert "Back in stock" in reason


# ------------------------------------------------------------------
# Full pipeline alert flow (mock servers capture real notifications)
# ------------------------------------------------------------------

class TestFullAlertPipeline:
    """
    Integration test: price drop -> should_alert -> send notifications -> verify.
    """

    def test_full_alert_flow(
        self,
        seeded_db,
        mock_slack: MockSlackServer,
        mock_smtp: MockSMTPServer,
        notification_env,
    ):
        """End-to-end: price drop triggers both Slack and email with correct content."""
        mock_slack.clear()
        mock_smtp.clear()

        drop = seeded_db["drop"]

        # 1. Decision
        config = AlertConfig(
            product_id=drop["product_id"],
            threshold_percent=5.0,
            alert_on_stock_change=True,
            last_alert_sent=None,
        )
        should_send, reason = should_alert(
            drop["new_snapshot"], drop["old_snapshot"], config
        )
        assert should_send is True

        # 2. Send alerts
        send_slack_alert(
            product_name="Roland TR-8S",
            old_price=drop["old_price"],
            new_price=drop["new_price"],
            percent_drop=drop["percent_drop"],
            product_url="https://www.thomann.co.uk/roland_tr_8s.htm",
            site="thomann",
        )
        send_email_alert(
            product_name="Roland TR-8S",
            old_price=drop["old_price"],
            new_price=drop["new_price"],
            percent_drop=drop["percent_drop"],
            product_url="https://www.thomann.co.uk/roland_tr_8s.htm",
        )

        # 3. Verify Slack
        assert len(mock_slack.messages) == 1
        slack_msg = mock_slack.messages[0]
        assert slack_msg.header_text == "Price Alert"
        assert slack_msg.contains_text("Roland TR-8S")
        assert slack_msg.contains_text("499.00")
        assert slack_msg.contains_text("549.00")
        assert slack_msg.contains_text("Thomann")

        # 4. Verify email
        assert len(mock_smtp.emails) == 1
        email = mock_smtp.emails[0]
        assert "Roland TR-8S" in email.subject
        assert email.contains_text("499.00")
        assert email.contains_text("549.00")

    def test_no_alert_when_price_stable(
        self,
        seeded_db,
        mock_slack: MockSlackServer,
        mock_smtp: MockSMTPServer,
        notification_env,
    ):
        """When price hasn't changed meaningfully, no notifications should be sent."""
        mock_slack.clear()
        mock_smtp.clear()

        product_id = seeded_db["product_ids"]["juno"]
        old = PriceSnapshot(
            product_id=product_id, price=559.00,
            currency="GBP", stock_status=StockStatus.IN_STOCK,
        )
        new = PriceSnapshot(
            product_id=product_id, price=558.50,
            currency="GBP", stock_status=StockStatus.IN_STOCK,
        )
        config = AlertConfig(
            product_id=product_id, threshold_percent=5.0,
            alert_on_stock_change=True, last_alert_sent=None,
        )

        should_send, _ = should_alert(new, old, config)
        assert should_send is False
        assert len(mock_slack.messages) == 0
        assert len(mock_smtp.emails) == 0
