"""
Notification system for price drop and stock change alerts.

Supports:
  - Slack webhook (Block Kit formatted, professional appearance)
  - Email via SMTP (HTML template with savings calculation)

Both channels are optional: if credentials are not configured in .env,
the notification is skipped with a warning rather than crashing the pipeline.
"""
import html
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from loguru import logger


def send_slack_alert(
    product_name: str,
    old_price: float,
    new_price: float,
    percent_drop: float,
    product_url: str,
    site: str,
) -> None:
    """Send a price drop alert to Slack with Block Kit rich formatting."""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")

    if not webhook_url:
        logger.warning("SLACK_WEBHOOK_URL not configured, skipping Slack notification")
        return

    savings = old_price - new_price

    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "Price Alert",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Product:*\n{product_name}"},
                    {"type": "mrkdwn", "text": f"*Retailer:*\n{site.title()}"},
                ],
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Was:*\n~£{old_price:.2f}~"},
                    {"type": "mrkdwn", "text": f"*Now:*\n£{new_price:.2f}"},
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":moneybag: *You Save:* £{savings:.2f} ({percent_drop:.1f}% off)",
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View Product"},
                        "url": product_url,
                        "style": "primary",
                    }
                ],
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Scraped at {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                    }
                ],
            },
        ]
    }

    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        logger.success(f"Slack notification sent for {product_name}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send Slack notification: {e}")


def send_email_alert(
    product_name: str,
    old_price: float,
    new_price: float,
    percent_drop: float,
    product_url: str,
) -> None:
    """Send an HTML email alert with savings calculation."""
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = os.getenv("SMTP_PORT")
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    email_from = os.getenv("EMAIL_FROM")
    email_to = os.getenv("EMAIL_TO")

    if not all([smtp_host, smtp_port, smtp_user, smtp_password, email_from, email_to]):
        logger.warning("Email credentials not fully configured, skipping email notification")
        return

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = (
            f"Price Drop: {product_name} - Save £{old_price - new_price:.2f}"
        )
        msg["From"] = email_from
        msg["To"] = email_to

        # Escape user-controlled values before embedding in HTML
        safe_name = html.escape(product_name)
        safe_url = html.escape(product_url)

        html_body = f"""
        <html>
          <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background-color: #4CAF50; color: white; padding: 20px; text-align: center;">
              <h2>Price Drop Alert!</h2>
            </div>
            <div style="padding: 20px; background-color: #f9f9f9;">
              <h3 style="color: #333;">{safe_name}</h3>
              <div style="background-color: white; padding: 15px; border-radius: 5px; margin: 10px 0;">
                <p style="font-size: 14px; color: #666; margin: 5px 0;">Previous Price:</p>
                <p style="font-size: 24px; color: #999; text-decoration: line-through; margin: 5px 0;">
                  £{old_price:.2f}
                </p>
                <p style="font-size: 14px; color: #666; margin: 15px 0 5px 0;">New Price:</p>
                <p style="font-size: 32px; color: #4CAF50; font-weight: bold; margin: 5px 0;">
                  £{new_price:.2f}
                </p>
              </div>
              <div style="background-color: #fff3cd; padding: 15px; border-radius: 5px; margin: 10px 0;">
                <p style="font-size: 18px; margin: 0;">
                  <strong>You Save: £{old_price - new_price:.2f} ({percent_drop:.1f}%)</strong>
                </p>
              </div>
              <div style="text-align: center; margin: 20px 0;">
                <a href="{safe_url}"
                   style="background-color: #4CAF50; color: white; padding: 12px 30px;
                          text-decoration: none; border-radius: 5px; display: inline-block;">
                  View Product
                </a>
              </div>
            </div>
            <div style="background-color: #333; color: #999; padding: 10px; text-align: center; font-size: 12px;">
              Automated price monitoring system
            </div>
          </body>
        </html>
        """

        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP_SSL(smtp_host, int(smtp_port), timeout=15) as server:
            server.login(smtp_user, smtp_password)
            server.send_message(msg)

        logger.success(f"Email notification sent for {product_name}")

    except Exception as e:
        logger.error(f"Failed to send email notification: {e}")
        # Don't re-raise — notification failures must not crash the pipeline
