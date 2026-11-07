"""Exercise the actual production entry point with browser-sized concurrent bursts."""
import asyncio
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx


def test_authenticated_asset_burst(tmp_path):
    root=Path(__file__).resolve().parents[1]
    html=(root/'public/admin-app/index.html').read_text(encoding='utf-8')
    assets=re.findall(r'(?:src|href)="(/admin-app/assets/[^"?]+)"',html)
    assert assets
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    origin=f'http://127.0.0.1:{port}'
    environment={**os.environ,'APP_ENV':'development','COOKIE_SECURE':'false','HOST':'127.0.0.1','PORT':str(port),'SITE_URL':origin,'DATA_DIR':str(tmp_path)}
    with (tmp_path/'server.log').open('wb') as log:
        server=subprocess.Popen([sys.executable,'-m','backend.run'],cwd=root,env=environment,stdout=log,stderr=log)
        try:
            with httpx.Client(base_url=origin,trust_env=False,timeout=5) as client:
                for _ in range(100):
                    try:
                        if client.get('/healthz').status_code==200:break
                    except httpx.HTTPError:pass
                    time.sleep(.1)
                else:raise AssertionError('Test server did not start')
                assert client.post('/api/setup',headers={'Origin':origin},json={'name':'Burst test','password':'burst-test-password','demo':False}).status_code==200
                cookie='; '.join(f'{key}={value}' for key,value in client.cookies.items())
            async def burst():
                async with httpx.AsyncClient(base_url=origin,trust_env=False,timeout=20,headers={'Cookie':cookie},limits=httpx.Limits(max_connections=64,max_keepalive_connections=64)) as client:
                    for _ in range(2):
                        responses=await asyncio.gather(*(client.get(assets[i%len(assets)]) for i in range(64)))
                        assert all(r.status_code==200 for r in responses),[r.status_code for r in responses]
                        assert all('immutable' in r.headers['cache-control'] for r in responses)
                    assert (await client.get('/api/private/overview')).status_code==200
            asyncio.run(burst())
        finally:
            server.terminate()
            try:server.wait(timeout=10)
            except subprocess.TimeoutExpired:server.kill();server.wait(timeout=5)
