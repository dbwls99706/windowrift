"""Opt-in local application state bridge: authenticated and never cross-network."""
from __future__ import annotations

from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, ProxyHandler, Request
from dataclasses import asdict
import json

from .portal_api import Capability, ObjectState, PortalError

MAX_RESPONSE = 1_000_000


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise PortalError("Adapter redirects are not permitted")


class LocalAppAdapter:
    """Connect only to an app that *explicitly* implements WindowRift v1."""
    def __init__(self, base_url: str, token: str):
        url = urlsplit(base_url)
        if (url.scheme != "http" or url.hostname not in
            ("127.0.0.1", "localhost", "::1") or url.username or url.password or
            url.query or url.fragment or url.path not in ("", "/")):
            raise ValueError("Adapter endpoint must be an HTTP loopback URL")
        if not token or len(token) < 16:
            raise ValueError("A 16+ character local app token is required")
        self.base_url, self.token = base_url.rstrip("/"), token
        # Ignore operating-system proxy settings and never follow HTTP redirects
        # to external domains with the bearer token.
        self._opener = build_opener(ProxyHandler({}), _NoRedirect())
        self._capability = Capability(**self._request("GET", "/windowrift/v1/capabilities"))
        if not all((self._capability.native_state, self._capability.native_identity,
                    self._capability.remove_from_source,
                    self._capability.return_to_source)):
            raise PortalError("The application must support real reversible native objects")

    @property
    def capability(self) -> Capability:
        return self._capability

    def _request(self, method, path, body=None):
        data = (json.dumps(body, separators=(",", ":")).encode("utf-8")
                if body is not None else None)
        request = Request(self.base_url + path, data=data, method=method,
                          headers={"X-WindowRift-Token": self.token,
                                   "Content-Type": "application/json",
                                   "Accept": "application/json"})
        try:
            with self._opener.open(request, timeout=4) as response:
                data = response.read(MAX_RESPONSE + 1)
        except (HTTPError, URLError, OSError, TimeoutError) as exc:
            raise PortalError("Native adapter request failed: " + str(exc)) from exc
        if len(data) > MAX_RESPONSE:
            raise PortalError("Oversized native adapter response")
        try:
            value = json.loads(data)
        except (UnicodeDecodeError, ValueError) as exc:
            raise PortalError("Native adapter returned invalid JSON") from exc
        if not isinstance(value, (dict, list)):
            raise PortalError("Native adapter JSON must be an object or list")
        return value

    def _state(self, result) -> ObjectState:
        if not isinstance(result, dict):
            raise PortalError("Native adapter did not return an object")
        try:
            state = ObjectState(**result)
        except (TypeError, ValueError) as exc:
            raise PortalError("Native adapter returned invalid state") from exc
        if (state.adapter != self.capability.app or
                state.kind not in self.capability.kinds or
                not state.native_identity):
            raise PortalError("Native identity or capabilities mismatch")
        return state

    def objects(self):
        values = self._request("GET", "/windowrift/v1/objects")
        if not isinstance(values, list) or len(values) > 256:
            raise PortalError("Invalid native objects list")
        return tuple(self._state(value) for value in values)

    def take(self, object_id):
        return self._state(self._request("POST", "/windowrift/v1/take",
                                         {"object_id": object_id}))

    def put(self, object_id, destination):
        return self._state(self._request("POST", "/windowrift/v1/put",
                                         {"object_id": object_id, "destination": destination}))

    def move(self, object_id, x, y):
        return self._state(self._request("POST", "/windowrift/v1/move",
                                         {"object_id": object_id, "screen_x": x, "screen_y": y}))

    def recover(self):
        records = self._request("POST", "/windowrift/v1/recover", {})
        if not isinstance(records, list) or not all(isinstance(v, str) for v in records):
            raise PortalError("Invalid recovery response")
        return records
