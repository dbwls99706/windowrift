"""Verify Minecraft Classic actually rendered in a browser, not a fake page.

The official public Classic site is fetched by Chrome at run time; none of its
JavaScript, textures, or game assets is bundled with this repository.
"""
from __future__ import annotations
import json
import sys
import time
from urllib.request import urlopen
from websockets.sync.client import connect


def inspect(port=9223):
    pages=json.load(urlopen(f'http://127.0.0.1:{port}/json',timeout=3))
    matches=[x for x in pages if x.get('type')=='page' and
             'classic.minecraft.net' in x.get('url','')]
    if len(matches)!=1:
        raise RuntimeError('Official Minecraft Classic browser tab not found')
    js='''(() => ({
      title:document.title,
      url:location.origin,
      visibleCanvases:[...document.querySelectorAll('canvas')]
         .filter(c=>c.width>120 && c.height>100 && c.getBoundingClientRect().width>100).length,
      body:document.body?.innerText?.slice(0,180),
      ready:document.readyState,
      webgl:typeof WebGLRenderingContext !== 'undefined'
    }))()'''
    with connect(matches[0]['webSocketDebuggerUrl'],origin='http://localhost') as ws:
        ws.send(json.dumps({'id':7,'method':'Runtime.evaluate',
                            'params':{'expression':js,'returnByValue':True}}))
        while 1:
            data=json.loads(ws.recv(timeout=5))
            if data.get('id')==7:
                return data['result']['result'].get('value')


def main():
    for _ in range(35):
        try:
            result=inspect()
            if result and result.get('visibleCanvases',0)>=1 and result.get('webgl'):
                print('ACTUAL_OFFICIAL_MINECRAFT_CLASSIC_CANVAS='+json.dumps(result))
                return
        except Exception as exc:
            result={'error':str(exc)}
        time.sleep(2)
    print('Minecraft Classic never exposed a visible WebGL game canvas: '+json.dumps(result),file=sys.stderr)
    raise SystemExit(1)

if __name__=='__main__':main()
