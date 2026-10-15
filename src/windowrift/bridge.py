"""Authenticated local WebSocket event stream for browser DOM interactions."""

from __future__ import annotations

import asyncio
import json
import secrets
import threading
from urllib.parse import parse_qs, urlsplit

from websockets.asyncio.server import serve


class BrowserBridge:
    def __init__(self, port: int = 8765) -> None:
        self.port = port
        self.token = secrets.token_urlsafe(24)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._clients: set = set()
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self.error: str | None = None

    async def _handler(self, ws) -> None:
        credentials = parse_qs(urlsplit(ws.request.path).query)
        if credentials.get("token") != [self.token]:
            await ws.close(code=1008, reason="Invalid connection token")
            return
        self._clients.add(ws)
        try:
            async for _ in ws:
                # Browsers cannot issue commands to the desktop app.
                pass
        finally:
            self._clients.discard(ws)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="windowrift-bridge", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=3)

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)

        async def service():
            async with serve(self._handler, "127.0.0.1", self.port, max_size=2048):
                self._ready.set()
                await asyncio.Future()

        try:
            loop.run_until_complete(service())
        except asyncio.CancelledError:
            pass
        except OSError as exc:
            self.error = str(exc)
            self._ready.set()
        finally:
            self._clients.clear()
            loop.close()
            self._loop = None

    def publish_actors(self, actors: list[dict]) -> None:
        if self._loop is None or not self._loop.is_running() or not self._clients:
            return
        message = json.dumps({"type": "actors", "actors": actors}, separators=(",", ":"))

        async def broadcast():
            await asyncio.gather(
                *(ws.send(message) for ws in tuple(self._clients)), return_exceptions=True
            )

        asyncio.run_coroutine_threadsafe(broadcast(), self._loop)

    def stop(self) -> None:
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        def stop_loop():
            for task in asyncio.all_tasks(loop):
                task.cancel()
        loop.call_soon_threadsafe(stop_loop)
        if self._thread:
            self._thread.join(timeout=2)
