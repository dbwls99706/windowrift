"""Opt-in Chrome DevTools probe for the local collision lab in CI.

Only a browser launched by the demo with remote debugging on loopback is used.
No credentials are logged, no arbitrary web pages are modified, and this script
is not part of WindowRift's ordinary user runtime.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from urllib.request import urlopen

from websockets.sync.client import connect


def evaluate(port: int, expression: str):
    with urlopen(f"http://127.0.0.1:{port}/json", timeout=3) as response:
        pages = json.load(response)
    matches = [page for page in pages if page.get('type') == 'page' and
               'WindowRift Collision Lab' in page.get('title', '')]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one live local Collision Lab tab; found {len(matches)}")
    ws = matches[0]['webSocketDebuggerUrl']
    with connect(ws, origin='http://localhost', open_timeout=3, close_timeout=3) as client:
        client.send(json.dumps({'id': 72, 'method': 'Runtime.evaluate', 'params': {
            'expression': expression, 'returnByValue': True, 'awaitPromise': True}}))
        while True:
            message = json.loads(client.recv(timeout=5))
            if message.get('id') == 72:
                if 'error' in message or 'exceptionDetails' in message.get('result', {}):
                    raise RuntimeError(f"Chrome evaluation rejected: {message}")
                return message['result']['result'].get('value')


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=9222)
    parser.add_argument('--token', default='')
    parser.add_argument('--target-file', type=Path)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--wait-connected', action='store_true',
                        help='Fail unless the local browser lab establishes the WebSocket')
    args = parser.parse_args()
    if args.check:
        for attempt in range(12):
            result = evaluate(args.port, "({impacts: Number(document.getElementById('impacts').textContent), connected: document.getElementById('connection').textContent})")
            if result['impacts'] > 0:
                print('BROWSER_DOM_IMPACT_CONFIRMED=' + json.dumps(result))
                return
            time.sleep(0.5)
        raise SystemExit('Actor never caused a real DOM impact on the local browser lab; last=' + json.dumps(result))
    if len(args.token) < 16 or args.target_file is None:
        parser.error('A session token >=16 characters and --target-file are required to connect')
    expression = '''(() => {
        const input = document.getElementById('token');
        input.value = ''' + json.dumps(args.token) + ''';
        document.getElementById('connect').click();
        input.value = '';
        const r = document.querySelector('[data-windowrift-target]').getBoundingClientRect();
        const side = Math.max(0, (outerWidth - innerWidth) / 2);
        const top = outerHeight - innerHeight - side;
        return { impact_point: [screenX + side + r.left + r.width/2,
                                screenY + top + r.top + r.height/2],
                 page: document.title };
    })()'''
    info = evaluate(args.port, expression)
    args.target_file.parent.mkdir(parents=True, exist_ok=True)
    args.target_file.write_text(json.dumps(info, indent=2)+'\n', encoding='utf-8')
    print('BROWSER_TARGET_MEASURED=' + json.dumps(info))
    if args.wait_connected:
        state = None
        for _ in range(16):
            state = evaluate(args.port, "document.getElementById('connection').textContent")
            if state == 'Connected to WindowRift':
                print('BROWSER_CONNECTED_CONFIRMED=' + state)
                return
            time.sleep(0.12)
        raise RuntimeError(f'Local browser lab WebSocket did not connect: {state}')


if __name__ == '__main__':
    run()
