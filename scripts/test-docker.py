"""Test a built image using a disposable named volume, never the site's data."""
import json
import subprocess
import time
import uuid
from pathlib import Path
import httpx

name = 'lin-v9-test-' + uuid.uuid4().hex[:8]
volume = name + '-data'
def docker(*args):
    return subprocess.check_output(['docker', *args], text=True).strip()

try:
    docker('volume', 'create', volume)
    docker('run', '-d', '--name', name, '--read-only', '--cap-drop=ALL',
           '--security-opt=no-new-privileges:true', '--memory=768m', '--cpus=1.5',
           '--pids-limit=128', '--tmpfs=/tmp:size=64m,noexec,nosuid',
           '-p', '127.0.0.1:4359:4317', '-e', 'SITE_URL=https://blog.test',
           '-v', volume + ':/app/data', 'lin-notebook:9')
    with httpx.Client(base_url='http://127.0.0.1:4359', headers={'Host':'127.0.0.1:4317'}, timeout=10, trust_env=False) as client:
        for attempt in range(60):
            try:
                if client.get('/healthz').status_code == 200: break
            except httpx.HTTPError: pass
            time.sleep(1)
        else: raise AssertionError(docker('logs', name))
        assert docker('exec', name, 'id', '-u') == '10001'
        assert client.get('/').status_code == 200
        assert client.get('/admin/login').status_code == 200
        assert client.post('/api/setup', json={}, headers={'Host':'blog.test','Origin':'https://blog.test'}).status_code == 403
        for path in ('/.env', '/backend/main.py', '/data/space.sqlite', '/api/docs'):
            assert client.get(path).status_code == 404, path
        assert client.get('/api/private/state').status_code == 401
        seed = """
from backend.storage import Store,set_meta
from backend.security import credentials
from backend.content import insert
from backend.validation import DEFAULT_PROFILE
from PIL import Image
from pathlib import Path
s=Store('/app/data')
salt,hashed=credentials('container-test-only-123')
with s.transaction() as db:
 set_meta(db,'account',{'name':'Container Test','salt':salt,'hash':hashed})
 set_meta(db,'profile',DEFAULT_PROFILE)
 for i in range(2): insert(db,'posts',{'title':'Persisted '+str(i),'slug':'persisted-'+str(i),'content':'Hello','excerpt':'Smoke test','status':'published','publishAt':'2026-01-01T00:00:00Z','category':'Test','tags':'','cover':'/uploads/persisted.png'})
Image.new('RGB',(2,2),'blue').save('/app/data/uploads/persisted.png')
assert not Path('/app/.env').exists()
assert not Path('/app/source').exists()
try: Path('/app/should-not-write').write_text('no')
except OSError: pass
else: raise AssertionError('Root filesystem writable')
"""
        docker('exec', name, 'python', '-c', seed)
        assert client.get('/api/public/posts/persisted-0').status_code == 200
        image = client.get('/uploads/persisted.png').content
        docker('restart', name)
        for attempt in range(30):
            try:
                if client.get('/healthz').status_code == 200: break
            except httpx.HTTPError: pass
            time.sleep(1)
        for i in range(2): assert client.get('/api/public/posts/persisted-'+str(i)).status_code == 200
        assert client.get('/uploads/persisted.png').content == image
        assert client.get('/api/status').json()['setup'] is False
        docker('exec', name, 'python', '-m', 'backend.cli', 'check')
        health = docker('exec', name, 'python', '-c', "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:4317/healthz').status==200")
        report = {'image':docker('inspect','--format={{.Image}}',name), 'passed':['non-root UID10001','readonly root','healthcheck command','production setup blocked','private routes isolated','source/env/database not served','two articles and image survive restart','SQLite integrity'], 'idle_stats':docker('stats','--no-stream','--format={{json .}}',name)}
        Path('test-results').mkdir(exist_ok=True)
        Path('test-results/docker-v9.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2))
finally:
    subprocess.run(['docker','rm','-f',name],capture_output=True)
    subprocess.run(['docker','volume','rm',volume],capture_output=True)
