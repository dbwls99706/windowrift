"""Opt-in local state handoff for the *bundled* Rift Arcade demo game.

This is deliberately not a general-purpose game-memory injector. It makes the
first-party example hide its source actor while WindowRift flies a visual actor
out, then show the original again on return. The real game loop keeps running.
"""

from __future__ import annotations

from dataclasses import dataclass
import hmac
import json
import socket
import time

MAX_PACKET = 512


@dataclass
class DemoHandoffState:
    token: str
    lifted: bool = False
    last_seen: float = 0.0
    lease_seconds: float = 2.5

    def expire(self, now: float | None = None) -> bool:
        """Restore the game after a crashed client stops sending keepalives."""
        at = time.monotonic() if now is None else now
        if self.lifted and at - self.last_seen > self.lease_seconds:
            self.lifted = False
            return True
        return False

    def handle(self, raw: bytes) -> dict[str, object]:
        if len(raw) > MAX_PACKET:
            return {"ok": False, "reason": "oversized"}
        try:
            message = json.loads(raw)
        except (ValueError, UnicodeError):
            return {"ok": False, "reason": "malformed"}
        if not isinstance(message, dict):
            return {"ok": False, "reason": "invalid-message"}
        token = message.get("token")
        if not isinstance(token, str) or not hmac.compare_digest(token, self.token):
            return {"ok": False, "reason": "unauthorized"}
        action = message.get("action")
        if action not in ("lift", "keepalive", "return", "status"):
            return {"ok": False, "reason": "unsupported-action"}
        if action == "lift":
            self.lifted = True
        elif action == "return":
            self.lifted = False
        if action in ("lift", "keepalive"):
            self.last_seen = time.monotonic()
        return {"ok": True, "lifted": self.lifted}


class DemoHandoffServer:
    """Only listens on loopback; poll from Tk's GUI thread."""

    def __init__(self, token: str, port: int = 8973):
        if len(token) < 12:
            raise ValueError("Demo handoff needs a token at least 12 characters long")
        self.state = DemoHandoffState(token)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(("127.0.0.1", port))
        self.socket.setblocking(False)
        self.port = self.socket.getsockname()[1]

    def poll(self) -> None:
        self.state.expire()
        for _ in range(8):
            try:
                data, address = self.socket.recvfrom(MAX_PACKET + 1)
            except BlockingIOError:
                break
            if address[0] != "127.0.0.1":
                continue
            reply = self.state.handle(data)
            self.socket.sendto(json.dumps(reply).encode("utf-8"), address)

    def close(self) -> None:
        self.socket.close()


def request_handoff(action: str, token: str, port: int = 8973, timeout: float = 0.5) -> bool:
    """Ask a first-party demo to hide or restore its own actor; no shell commands."""
    if action not in ("lift", "keepalive", "return", "status"):
        raise ValueError("Only demo lift, keepalive, return and status actions are allowed")
    if len(token) < 12:
        raise ValueError("Invalid handoff token")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.settimeout(timeout)
        client.sendto(json.dumps({"token": token, "action": action}).encode("utf-8"),
                      ("127.0.0.1", port))
        try:
            raw, _ = client.recvfrom(MAX_PACKET)
        except socket.timeout:
            return False
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeError):
        return False
    return isinstance(result, dict) and result.get("ok") is True
