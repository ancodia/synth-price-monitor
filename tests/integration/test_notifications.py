"""
Integration tests for Slack and email notification sending.

Validates that send_slack_alert and send_email_alert produce correctly
formatted messages captured by the mock servers.
"""

from notifications import send_slack_alert, send_email_alert

from .mock_services import MockSlackServer, MockSMTPServer


class TestSlackNotification:
    """Test that Slack webhook sends correctly formatted messages."""

    def test_slack_alert_sends_to_mock(
        self, mock_slack: MockSlackServer, notification_env
    ):
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

    def test_slack_payload_has_header(
        self, mock_slack: MockSlackServer, notification_env
    ):
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

    def test_slack_payload_contains_product_name(
        self, mock_slack: MockSlackServer, notification_env
    ):
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

    def test_slack_payload_contains_prices(
        self, mock_slack: MockSlackServer, notification_env
    ):
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

    def test_slack_payload_contains_savings(
        self, mock_slack: MockSlackServer, notification_env
    ):
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

    def test_slack_payload_contains_retailer(
        self, mock_slack: MockSlackServer, notification_env
    ):
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

    def test_slack_payload_contains_product_url(
        self, mock_slack: MockSlackServer, notification_env
    ):
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

    def test_email_alert_sends_to_mock(
        self, mock_smtp: MockSMTPServer, notification_env
    ):
        mock_smtp.clear()
        send_email_alert(
            product_name="Roland TR-8S",
            old_price=549.00,
            new_price=499.00,
            percent_drop=9.1,
            product_url="https://www.thomann.co.uk/roland_tr_8s.htm",
        )
        assert len(mock_smtp.emails) == 1

    def test_email_subject_contains_product_name(
        self, mock_smtp: MockSMTPServer, notification_env
    ):
        mock_smtp.clear()
        send_email_alert(
            product_name="Roland TR-8S",
            old_price=549.00,
            new_price=499.00,
            percent_drop=9.1,
            product_url="https://www.thomann.co.uk/roland_tr_8s.htm",
        )
        assert "Roland TR-8S" in mock_smtp.emails[0].subject

    def test_email_subject_contains_savings(
        self, mock_smtp: MockSMTPServer, notification_env
    ):
        mock_smtp.clear()
        send_email_alert(
            product_name="Roland TR-8S",
            old_price=549.00,
            new_price=499.00,
            percent_drop=9.1,
            product_url="https://www.thomann.co.uk/roland_tr_8s.htm",
        )
        assert "50.00" in mock_smtp.emails[0].subject

    def test_email_body_contains_prices(
        self, mock_smtp: MockSMTPServer, notification_env
    ):
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

    def test_email_body_contains_product_url(
        self, mock_smtp: MockSMTPServer, notification_env
    ):
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
