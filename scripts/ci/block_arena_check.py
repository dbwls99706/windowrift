"""Read real browser DOM after keyboard-controlled Minecraft-to-Chrome play.

CI only: connects to a purpose-launched local Chrome DevTools endpoint. It
never changes Minecraft's game internals or injects fake DOM success values.
"""
from __future__ import annotations

import argparse
import json
from urllib.request import urlopen
import time
import subprocess
from websockets.sync.client import connect


def evaluate(expression: str, port: int = 9222, *, browser_title: str = 'WindowRift Block Arena'):
    with urlopen(f'http://127.0.0.1:{port}/json', timeout=4) as response:
        pages = json.load(response)
    matches = [p for p in pages if p.get('type') == 'page' and browser_title in p.get('title', '')]
    if len(matches) != 1:
        raise RuntimeError(f'Expected one live Block Arena Chrome tab, found {len(matches)}')
    with connect(matches[0]['webSocketDebuggerUrl'], origin='http://localhost', open_timeout=4) as ws:
        ws.send(json.dumps({'id': 19, 'method': 'Runtime.evaluate', 'params': {
            'expression': expression, 'returnByValue': True, 'awaitPromise': True}}))
        while True:
            result = json.loads(ws.recv(timeout=7))
            if result.get('id') != 19:
                continue
            if 'error' in result or 'exceptionDetails' in result.get('result', {}):
                raise RuntimeError('Chrome evaluation failed: ' + json.dumps(result))
            return result['result']['result'].get('value')


def snapshot():
    return evaluate("""(() => ({
        title: document.title,
        connected: document.getElementById('connection').textContent,
        mined: Number(document.getElementById('blocks-mined').textContent),
        built: Number(document.getElementById('blocks-built').textContent),
        impacts: Number(document.getElementById('impacts').textContent),
        blocks: document.querySelectorAll('#blocks .block').length,
        builtNodes: document.querySelectorAll('#blocks .block.added').length,
        blockLabels: [...document.querySelectorAll('#blocks .block')]
            .map(el => el.getAttribute('data-id')),
        lastActor: window.__riftLastActor || null,
    }))()""")


def wait_for_connected(token: str) -> dict:
    if len(token) < 16:
        raise ValueError('Browser bridge token must have 16+ characters')
    expression = """(() => {
        document.getElementById('token').value = TOKEN;
        document.getElementById('connect').click();
        document.getElementById('token').value = '';
    })()""".replace('TOKEN', json.dumps(token))
    evaluate(expression)
    for _ in range(40):
        state = snapshot()
        if state['connected'] == 'Connected to WindowRift':
            print('BROWSER_CONNECTED_CONFIRMED=' + json.dumps({'title': state['title']}), flush=True)
            return state
        time.sleep(.15)
    raise RuntimeError('Minecraft browser arena did not connect to localhost bridge; ' + json.dumps(state))


def validate(*, require_connected: bool) -> dict:
    state = snapshot()
    if (state['mined'] < 1 or state['built'] < 1 or state['builtNodes'] < 1 or
            (require_connected and state['connected'] != 'Connected to WindowRift')):
        raise RuntimeError('Real HTML mine/place interaction did not occur: ' + json.dumps(state))
    print('MINECRAFT_BROWSER_DOM_PLAY_CONFIRMED=' + json.dumps(state), flush=True)
    return state


def reload_and_verify() -> None:
    before = validate(require_connected=False)
    evaluate('window.location.reload(); true')
    for _ in range(35):
        try:
            after = snapshot()
            if (after['mined'] >= before['mined'] and
                    after['built'] >= before['built'] and after['builtNodes'] >= 1):
                print('BROWSER_STATE_SURVIVED_RELOAD=' + json.dumps(after), flush=True)
                return
        except (OSError, KeyError, RuntimeError):
            pass
        time.sleep(.2)
    raise RuntimeError('Block Arena state was not preserved across a real page reload')


def send_key(controller: str, key: str, *, hold: float = 0.12) -> None:
    """Send actual X11 KeyPress and KeyRelease events to the Tk controller."""
    subprocess.run(['xdotool', 'keydown', '--window', controller, key], check=True)
    time.sleep(hold)
    subprocess.run(['xdotool', 'keyup', '--window', controller, key], check=True)


def drive_to_block(controller: str) -> None:
    """Reach a Chrome DOM block by pressing keys, never setting actor coordinates."""
    subprocess.run(['xdotool', 'windowactivate', '--sync', controller], check=True)
    for step in range(18):
        geometry = evaluate("""(() => {
          const actor = window.__riftLastActor;
          const block = document.querySelector('#blocks .block');
          if (!actor || !block) return null;
          const rect = block.getBoundingClientRect();
          const side = Math.max(0, (outerWidth - innerWidth) / 2);
          const originX = screenX + side;
          const originY = screenY + outerHeight - innerHeight - side;
          return {actor, targetX: originX + rect.left + rect.width/2,
                  targetY: originY + rect.top + rect.height/2};
        })()""")
        if not geometry:
            time.sleep(.15)
            continue
        actor = geometry['actor']
        dx = geometry['targetX'] - actor['x'] - actor['width']/2
        dy = geometry['targetY'] - actor['y'] - actor['height']/2
        print('X11_KEYBOARD_PLAYER_POSITION=' + json.dumps({'step': step, 'x': actor['x'],
              'y': actor['y'], 'dx': round(dx), 'dy': round(dy)}), flush=True)
        if abs(dx) <= 60 and abs(dy) <= 115:
            send_key(controller, 'space', hold=.09)
            time.sleep(.22)
            send_key(controller, 'e', hold=.11)
            time.sleep(.25)
            send_key(controller, 'f', hold=.11)
            time.sleep(.35)
            return
        direction = 'd' if dx > 0 else 'a'
        send_key(controller, direction, hold=min(.45, max(.11, abs(dx)/390 * .63)))
        time.sleep(.10)
    raise RuntimeError('Real keyboard control could not reach the browser block; ' +
                       json.dumps(geometry))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--token', default='')
    parser.add_argument('--connect', action='store_true')
    parser.add_argument('--reset', action='store_true')
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--reload-verify', action='store_true')
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--drive', metavar='X11_WINDOW_ID', help='Use real keyboard events to mine and place')
    args = parser.parse_args()
    if args.reset:
        evaluate("document.getElementById('reset').click(); true")
        print('MINECRAFT_ARENA_RESET', flush=True)
    if args.connect:
        wait_for_connected(args.token)
    if args.status:
        print('MINECRAFT_ARENA=' + json.dumps(snapshot()), flush=True)
    if args.drive:
        drive_to_block(args.drive)
    if args.verify:
        validate(require_connected=True)
    if args.reload_verify:
        reload_and_verify()


if __name__ == '__main__':
    main()
