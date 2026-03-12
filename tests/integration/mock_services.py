"""
Mock notification services for e2e testing.

Provides:
  - MockSlackServer: HTTP server that captures Slack webhook POSTs
  - MockSMTPServer: SMTP server that captures emails in memory

Both run in background threads and expose captured messages for assertions.
"""

import json
import threading
import time
from dataclasses import dataclass, field
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import List, Optional

from aiosmtpd.controller import Controller


# ------------------------------------------------------------------
# Mock Slack webhook server
# ------------------------------------------------------------------


@dataclass
class SlackMessage:
    """A captured Slack webhook payload."""

    payload: dict
    received_at: float = field(default_factory=time.time)

    @property
    def blocks(self) -> list:
        return self.payload.get("blocks", [])

    @property
    def header_text(self) -> Optional[str]:
        for block in self.blocks:
            if block.get("type") == "header":
                return block.get("text", {}).get("text")
        return None

    @property
    def fields(self) -> dict:
        """Extract all mrkdwn fields into a flat dict of label -> value."""
        result = {}
        for block in self.blocks:
            if block.get("type") == "section" and "fields" in block:
                for f in block["fields"]:
                    text = f.get("text", "")
                    if "\n" in text:
                        label, value = text.split("\n", 1)
                        result[label.strip("* ")] = value.strip()
        return result

    def contains_text(self, text: str) -> bool:
        """Check if any block contains the given text (case-insensitive)."""
        raw = json.dumps(self.payload).lower()
        return text.lower() in raw


class _SlackHandler(BaseHTTPRequestHandler):
    """HTTP handler that captures POST bodies as Slack messages."""

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            payload = json.loads(body)
            self.server.captured_messages.append(SlackMessage(payload=payload))
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()

    def log_message(self, format, *args):
        """Suppress default HTTP access logging during tests."""
        pass


class MockSlackServer:
    """
    In-process HTTP server that impersonates the Slack webhook endpoint.

    Usage:
        server = MockSlackServer(port=9100)
        server.start()
        assert len(server.messages) == 1
        assert server.messages[0].contains_text("Price Alert")
        server.stop()
    """

    def __init__(self, port: int = 9100):
        self.port = port
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._server = HTTPServer(("127.0.0.1", self.port), _SlackHandler)
        self._server.captured_messages: List[SlackMessage] = []
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._thread.join(timeout=5)
            self._server.server_close()

    @property
    def messages(self) -> List[SlackMessage]:
        return self._server.captured_messages if self._server else []

    @property
    def webhook_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/webhook"

    def clear(self):
        if self._server:
            self._server.captured_messages.clear()


# ------------------------------------------------------------------
# Mock SMTP server
# ------------------------------------------------------------------


@dataclass
class CapturedEmail:
    """A captured email message."""

    peer: tuple
    mail_from: str
    rcpt_tos: list
    data: str  # raw email content (headers + body)
    received_at: float = field(default_factory=time.time)

    @property
    def subject(self) -> str:
        import email.header

        for line in self.data.split("\n"):
            if line.lower().startswith("subject:"):
                raw = line.split(":", 1)[1].strip()
                parts = email.header.decode_header(raw)
                return "".join(
                    part.decode(enc or "utf-8") if isinstance(part, bytes) else part
                    for part, enc in parts
                )
        return ""

    def contains_text(self, text: str) -> bool:
        import email as email_lib
        import quopri
        import base64

        msg = email_lib.message_from_string(self.data)
        for part in msg.walk():
            cte = part.get("Content-Transfer-Encoding", "").lower()
            payload = part.get_payload()
            if isinstance(payload, str):
                if cte == "base64":
                    try:
                        decoded = base64.b64decode(payload).decode(
                            "utf-8", errors="replace"
                        )
                    except Exception:
                        decoded = payload
                elif cte == "quoted-printable":
                    try:
                        decoded = quopri.decodestring(payload.encode()).decode(
                            "utf-8", errors="replace"
                        )
                    except Exception:
                        decoded = payload
                else:
                    decoded = payload
                if text.lower() in decoded.lower():
                    return True
        return text.lower() in self.data.lower()


class _CapturingHandler:
    """aiosmtpd handler that stores all received emails."""

    def __init__(self):
        self.captured: List[CapturedEmail] = []

    async def handle_DATA(self, server, session, envelope):
        self.captured.append(
            CapturedEmail(
                peer=session.peer,
                mail_from=envelope.mail_from,
                rcpt_tos=list(envelope.rcpt_tos),
                data=envelope.content.decode("utf-8", errors="replace"),
            )
        )
        return "250 OK"


class MockSMTPServer:
    """
    In-process SMTP server that captures emails for test assertions.

    Usage:
        server = MockSMTPServer(port=9025)
        server.start()
        assert len(server.emails) == 1
        assert "Price Drop" in server.emails[0].subject
        server.stop()
    """

    def __init__(self, port: int = 9025):
        self.port = port
        self._handler = _CapturingHandler()
        self._controller: Optional[Controller] = None

    def start(self):
        self._controller = Controller(
            self._handler,
            hostname="127.0.0.1",
            port=self.port,
        )
        self._controller.start()

    def stop(self):
        if self._controller:
            self._controller.stop()

    @property
    def emails(self) -> List[CapturedEmail]:
        return self._handler.captured

    def clear(self):
        self._handler.captured.clear()
