import asyncio
import json
import socket

import pytest
import websockets

from windowrift.bridge import BrowserBridge


def free_local_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


@pytest.mark.asyncio
async def test_secure_websocket_rejects_wrong_token_and_broadcasts_actor():
    bridge = BrowserBridge(port=free_local_port())
    bridge.start()
    try:
        async with websockets.connect(f'ws://127.0.0.1:{bridge.port}/?token=wrong') as ws:
            with pytest.raises(websockets.exceptions.ConnectionClosedError):
                await ws.recv()
        async with websockets.connect(
            f'ws://127.0.0.1:{bridge.port}/?token={bridge.token}'
        ) as ws:
            for _ in range(20):
                bridge.publish_actors([{'id': 0, 'x': 25, 'y': 50, 'width': 30, 'height': 30}])
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=0.05)
                    break
                except asyncio.TimeoutError:
                    pass
            else:
                raise AssertionError('did not broadcast actor data')
            payload = json.loads(message)
            assert payload['type'] == 'actors'
            assert payload['actors'][0]['x'] == 25
    finally:
        bridge.stop()
