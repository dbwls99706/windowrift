"""Fetch official Mojang 1.21.1 server jar, verify its SHA-1, never redistribute."""
from __future__ import annotations
import hashlib,json,os
from pathlib import Path
from urllib.request import urlopen
VERSION='1.21.1'
MANIFEST='https://piston-meta.mojang.com/mc/game/version_manifest_v2.json'

def fetch(url):
    if not url.startswith(('https://piston-meta.mojang.com/','https://piston-data.mojang.com/')):
        raise ValueError('Only official Mojang hosts permitted')
    with urlopen(url,timeout=45) as r:
        data=r.read(75*1024*1024+1)
    if len(data)>75*1024*1024:
        raise ValueError('Download exceeds maximum size')
    return data

def main():
    version_manifest=json.loads(fetch(MANIFEST))
    found=[x for x in version_manifest['versions'] if x['id']==VERSION]
    if len(found)!=1:
        raise RuntimeError('Pinned Minecraft server version unavailable')
    detail=json.loads(fetch(found[0]['url']))
    server=detail['downloads']['server']
    payload=fetch(server['url'])
    digest=hashlib.sha1(payload).hexdigest()
    if digest!=server['sha1']:
        raise RuntimeError('Official Minecraft jar checksum mismatch')
    path=Path(os.environ.get('RUNNER_TEMP','/tmp'))/'windowrift-real-minecraft-server.jar'
    path.write_bytes(payload)
    print('OFFICIAL_MOJANG_SERVER_VERIFIED='+json.dumps({'version':VERSION,'sha1':digest,'size':len(payload)}),flush=True)
    with open(os.environ.get('GITHUB_ENV','/dev/null'),'a') as f:
        f.write('WR_MINECRAFT_SERVER='+str(path)+'\n')

if __name__=='__main__':main()
