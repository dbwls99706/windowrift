import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import pytest

from windowrift.http_adapter import LocalAppAdapter
from windowrift.portal_api import PortalError


def test_urls_outside_loopback_are_rejected():
    token = "local-mock-secret-long-enough"
    for endpoint in (
        "https://example.com", "http://example.com",
        "http://127.0.0.1:8000/app", "http://user:pw@127.0.0.1:8000",
        "http://127.0.0.1:8000/?a=1",
    ):
        with pytest.raises(ValueError):
            LocalAppAdapter(endpoint, token)


def test_second_opt_in_application_real_state_roundtrip():
    """Proof of the plug-in protocol, not a claim that all external apps work."""
    token = "private-session-token-long-enough"
    record = {
        "adapter":"sample:tasks", "object_id":"native-42", "kind":"task",
        "native_identity":"sample-task-42", "phase":"inside",
        "screen_x":40, "screen_y":80, "payload":{"title":"Prepare release"}
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): return
        def _write(self, obj):
            raw = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        def _handle(self):
            if self.headers.get("X-WindowRift-Token") != token:
                self.send_error(403); return
            if self.path.endswith("/capabilities"):
                return self._write({
                    "app":"sample:tasks", "kinds":["task"], "native_state":True,
                    "native_identity":True, "remove_from_source":True,
                    "return_to_source":True, "desktop_visual":True
                })
            if self.path.endswith("/objects"): return self._write([record])
            length = int(self.headers.get("Content-Length","0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            if body.get("object_id") != record["object_id"] and not self.path.endswith("/recover"):
                self.send_error(409); return
            if self.path.endswith("/take"):
                record["phase"] = "outside"
            elif self.path.endswith("/put"):
                record["phase"] = "inside"
                record["payload"]["destination"] = body["destination"]
            elif self.path.endswith("/move"):
                record["screen_x"] = body["screen_x"]
                record["screen_y"] = body["screen_y"]
            elif self.path.endswith("/recover"):
                return self._write([])
            return self._write(record)
        do_GET = _handle
        do_POST = _handle

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        adapter = LocalAppAdapter(f"http://127.0.0.1:{port}", token)
        assert adapter.objects()[0].object_id == "native-42"
        assert adapter.take("native-42").phase == "outside"
        moved = adapter.move("native-42", 700, 200)
        assert moved.native_identity == "sample-task-42"
        assert moved.screen_x == 700
        assert adapter.put("native-42", {"list":"done"}).phase == "inside"
        assert adapter.objects()[0].payload["destination"]["list"] == "done"
        assert adapter.recover() == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_invalid_token_refused():
    with pytest.raises(ValueError):
        LocalAppAdapter("http://127.0.0.1:8000", "123")
