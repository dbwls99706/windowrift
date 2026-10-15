import json
import socket
import threading
import time

from windowrift.demo_handoff import DemoHandoffServer, DemoHandoffState, MAX_PACKET, request_handoff


TOKEN = "integration-check-token"


def packet(action, token=TOKEN):
    return json.dumps({"action": action, "token": token}).encode()


def test_handoff_denies_unauthorized_and_unrecognized_actions():
    state = DemoHandoffState(TOKEN)
    assert state.handle(packet("lift", "bad-token"))["reason"] == "unauthorized"
    assert state.handle(b"not-json")["reason"] == "malformed"
    assert state.handle(b"[]")["reason"] == "invalid-message"
    assert state.handle(b"x" * (MAX_PACKET + 1))["reason"] == "oversized"
    assert state.handle(packet("flash"))["reason"] == "unsupported-action"
    assert not state.lifted


def test_handoff_state_changes_only_on_explicit_commands():
    state = DemoHandoffState(TOKEN)
    assert state.handle(packet("lift")) == {"ok": True, "lifted": True}
    assert state.handle(packet("status")) == {"ok": True, "lifted": True}
    assert state.handle(packet("return")) == {"ok": True, "lifted": False}


def test_handoff_server_loopback_request_roundtrip():
    server = DemoHandoffServer(TOKEN, port=0)
    stop = threading.Event()

    def worker():
        while not stop.wait(0.005):
            server.poll()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        assert request_handoff("lift", TOKEN, port=server.port)
        assert server.state.lifted
        assert not request_handoff("return", "wrong-long-token", port=server.port)
        assert server.state.lifted
        assert request_handoff("return", TOKEN, port=server.port)
        assert not server.state.lifted
    finally:
        stop.set()
        thread.join(timeout=1)
        server.close()


def test_handoff_lease_restores_after_crashed_portal():
    state = DemoHandoffState(TOKEN)
    assert state.handle(packet("lift"))["ok"]
    assert state.lifted
    assert not state.expire(state.last_seen + state.lease_seconds / 2)
    assert state.handle(packet("keepalive"))["ok"]
    assert not state.expire(state.last_seen + state.lease_seconds / 2)
    assert state.expire(state.last_seen + state.lease_seconds + 0.1)
    assert not state.lifted
