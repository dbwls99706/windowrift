"""Verify a *real unrelated external website* in separately launched Chrome.

Never injects scripts or DOM nodes; Chrome DevTools is read-only except for a
user-requested navigation on the dedicated ephemeral CI browser profile.
"""
from __future__ import annotations
import argparse
import json
import time
from urllib.request import urlopen
from urllib.parse import urlsplit
from websockets.sync.client import connect


ALLOWED_UNRELATED_HOSTS = {'en.wikipedia.org', 'www.wikipedia.org', 'example.com', 'www.gnu.org'}


def page(port=9222):
    pages=json.load(urlopen(f'http://127.0.0.1:{port}/json',timeout=4))
    matches=[p for p in pages if p.get('type')=='page']
    if len(matches)!=1:
        raise RuntimeError(f'Expected one independent website tab, got {len(matches)}')
    return matches[0]


def send(ws, method, params=None):
    ws.send(json.dumps({'id':4,'method':method,'params':params or {}}))
    while True:
        item=json.loads(ws.recv(timeout=6))
        if item.get('id')==4:
            if 'error' in item or 'exceptionDetails' in item.get('result',{}):
                raise RuntimeError(f'Chrome rejected {method}: {item}')
            return item.get('result',{})


def inspect(port=9222):
    tab=page(port)
    with connect(tab['webSocketDebuggerUrl'],origin='http://localhost',open_timeout=4) as ws:
        result=send(ws,'Runtime.evaluate',{'expression':
             '''(() => ({title:document.title, url:location.href, ready:document.readyState,
                       contentLength:document.body?.innerText?.length||0,
                       injectedOverlayNodes:document.querySelectorAll('[data-windowrift-block]').length}))()''',
                'returnByValue':True})
        return result['result'].get('value') or {}


def navigate(url,port=9222):
    if urlsplit(url).hostname not in ALLOWED_UNRELATED_HOSTS:
        raise ValueError('Test navigation must remain on a known unrelated external website')
    tab=page(port)
    with connect(tab['webSocketDebuggerUrl'],origin='http://localhost',open_timeout=4) as ws:
        send(ws,'Page.navigate',{'url':url})


def verify(port=9222, *, timeout=35):
    end=time.monotonic()+timeout
    seen=None
    while time.monotonic()<end:
        try:
            info=inspect(port)
            if (urlsplit(info.get('url','')).hostname in ALLOWED_UNRELATED_HOSTS
                    and info.get('ready')=='complete'
                    and info.get('contentLength',0)>=80
                    and info.get('injectedOverlayNodes')==0):
                print('REAL_UNRELATED_WEBSITE_VERIFIED='+json.dumps(info),flush=True)
                return info
            seen=info
        except (OSError, KeyError,RuntimeError,ValueError) as e:
            seen={'error':str(e)}
        time.sleep(.6)
    raise RuntimeError('Unrelated website was not loaded or injected DOM was found: '+json.dumps(seen))


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--port',type=int,default=9222)
    p.add_argument('--navigate',default='')
    p.add_argument('--timeout',type=float,default=35)
    args=p.parse_args()
    if args.navigate:
        navigate(args.navigate,args.port)
    verify(args.port,timeout=args.timeout)


if __name__=='__main__':main()
