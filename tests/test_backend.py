import asyncio
import base64
import io
import json
import sqlite3
import subprocess
import time
from pathlib import Path
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor
import httpx
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from backend.main import create_app
from backend.storage import Store,meta,set_meta,dumps
from backend.security import password_hash,sha,millis
from backend.git_activity import GitActivity


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path),base_url='http://testserver',headers={'Origin':'http://testserver'}) as c:
        r=c.post('/api/setup',json={'name':'Lin','password':'test-password-123','demo':True})
        assert r.status_code==200,r.text
        yield c


def post(**kwargs):
    return {'title':'Test','slug':'test-post','excerpt':'Summary','content':'## Hello\n\nText','category':'技术笔记','status':'published','publishAt':datetime.now(timezone.utc).isoformat(),**kwargs}


def png():
    buf=io.BytesIO(); Image.new('RGB',(2,2),'blue').save(buf,format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode()


def test_public_isolation_csrf_and_reader_permissions(client):
    assert client.post('/api/studio/posts',json=post(status='private')).status_code==201
    assert client.get('/api/public/posts/test-post').status_code==404
    assert 'test-post' not in client.get('/rss.xml').text
    assert client.put('/api/admin/site',json={},headers={'Origin':'https://evil.test'}).status_code==403
    assert client.post('/api/admin/users',json={'username':'reader','name':'Reader','password':'reader-password'}).status_code==201
    client.post('/api/logout')
    for path in ['/api/private/state','/api/studio/posts','/api/admin/site','/space-tools/tasks']:
        assert client.get(path).status_code==401
    assert client.post('/api/login',json={'username':'reader','password':'reader-password'}).status_code==200
    for path in ['/api/private/state','/api/studio/posts','/api/studio/git','/api/admin/site','/space-tools/tasks']:
        assert client.get(path).status_code==403
    assert client.get('/api/studio/profile').status_code==200
    assert client.post('/api/studio/posts',json=post()).status_code==403


def test_crud_versions_idempotency_and_validation(client):
    b={'title':'Task','due':'2026-10-26','clientId':'ebc37b1c-1063-44b3-94d9-00a37d118c64'}
    r=client.post('/api/private/records/tasks',json=b); assert r.status_code==201,r.text
    row=r.json(); assert client.post('/api/private/records/tasks',json=b).json()['id']==row['id']
    assert client.post('/api/private/records/tasks',json={**b,'title':'different'}).status_code==409
    url='/api/private/records/tasks/'+row['id']
    assert client.put(url,json={**row,'status':'done'}).status_code==200
    assert client.put(url,json=row).status_code==409
    assert client.request('DELETE',url,json={'version':1}).status_code==409
    assert client.request('DELETE',url,json={'version':2}).status_code==200
    for bad in ['2026-02-30','not-date']:
        assert client.post('/api/private/records/tasks',json={'title':'bad','due':bad}).status_code==400
    assert client.post('/api/private/records/health',json={'date':'2026-10-26','steps':True}).status_code==400


def test_comments_moderation_and_markup(client):
    r=client.post('/api/studio/posts',json=post()); assert r.status_code==201,r.text
    url='/api/public/posts/test-post/comments'
    assert client.post(url,json={'name':'Reader','content':'Hello <script>alert(1)</script>'}).status_code==202
    assert client.get(url).json()==[]
    row=client.get('/api/admin/comments').json()[0]
    assert client.put('/api/admin/comments/'+row['id'],json={'status':'approved','version':1}).status_code==200
    assert len(client.get(url).json())==1
    assert client.put('/api/admin/comments/'+row['id'],json={'status':'rejected','version':1}).status_code==409
    rendered=client.post('/api/studio/preview',json={'content':'<script>alert(1)</script>\n\n[bad](javascript:alert(1))\n\n## Title\n\n| A | B |\n|---|---|\n|1|2|'}).json()
    assert '<script>' not in rendered['html'] and 'href="javascript:' not in rendered['html']
    assert '<table>' in rendered['html'] and rendered['headings'][0]['id']=='section-1'


def test_images_access_paths_and_decode(client):
    r=client.post('/api/studio/upload',json={'data':png()}); assert r.status_code==200,r.text
    url=r.json()['url']; assert client.get(url).status_code==200
    cookie=client.cookies.get('space_session'); client.cookies.clear()
    assert client.get(url).status_code==404
    client.cookies.set('space_session',cookie)
    p=client.post('/api/studio/posts',json=post(cover=url)).json()
    client.cookies.clear(); assert client.get(url).status_code==200
    client.cookies.set('space_session',cookie)
    assert client.put('/api/studio/posts/'+p['id'],json={**p,'status':'private'}).status_code==200
    assert client.post('/api/studio/upload',json={'data':'data:image/png;base64,'+base64.b64encode(b'\x89PNG\r\n\x1a\ninvalid').decode()}).status_code==400
    for path in ['/.env','/backend/main.py','/data/space.sqlite','/index.html','/web/index.html','/assets/manifest.json','/assets/%2e%2e/.env','/blog-app/index.html']:
        assert client.get(path).status_code==404,path


def test_backup_and_ingest(client):
    token=client.post('/api/private/tokens',json={'name':'Robot'}).json()['token']
    body={'kind':'health','source':'robot','key':'one','data':{'date':'2020-01-01','steps':42}}
    headers={'Authorization':'Bearer '+token}
    a=client.post('/api/ingest',json=body,headers=headers); assert a.status_code==200,a.text
    b=client.post('/api/ingest',json=body,headers=headers); assert b.json()['replayed']
    assert client.post('/api/ingest',json={**body,'data':{'date':'2020-01-01','steps':43}},headers=headers).status_code==409
    backup=client.get('/api/private/backup').json()
    assert client.post('/api/private/restore',json=backup).status_code==200
    assert client.post('/api/private/restore',json={**backup,'records':backup['records']+[backup['records'][0]]}).status_code==400
    assert client.get('/api/status').json()['authenticated']


def test_v8_node_password_and_database_migration(tmp_path):
    salt='abc123'; password='admin123'
    expected=subprocess.check_output(['node','--input-type=module','-e',"import {scryptSync} from 'node:crypto';process.stdout.write(scryptSync('admin123','abc123',64).toString('hex'))"],text=True)
    assert password_hash(password,salt)==expected
    store=Store(tmp_path)
    with store.connect() as db:
        db.executescript((Path(__file__).parent/'fixtures/v8-schema.sql').read_text(encoding='utf-8'))
    with store.connect() as db:
        set_meta(db,'account',{'name':'Original','salt':salt,'hash':expected}); db.execute('PRAGMA user_version=8')
        db.execute("INSERT INTO journal VALUES('original','moments','owner',?,1,'2026-01-01','2026-01-01')",(dumps({'status':'published','content':'online article','images':[]}),))
        for i in range(2):
            db.execute("INSERT INTO records(id,kind,data,created,updated,userId) VALUES(?,'posts',?,'2026-01-01','2026-01-01','owner')",(f'online-{i}',dumps(post(slug=f'online-{i}',cover='/uploads/online.png'))))
    image=Image.new('RGB',(2,2),'blue'); image.save(tmp_path/'uploads/online.png')
    original=(tmp_path/'uploads/online.png').read_bytes()
    with TestClient(create_app(tmp_path),headers={'Origin':'http://testserver'}) as c:
        assert c.post('/api/login',json={'username':'admin','password':'admin123'}).status_code==200
        assert c.get('/api/public/journal/moments').json()[0]['content']=='online article'
        for i in range(2): assert c.get(f'/api/public/posts/online-{i}').status_code==200
        assert c.get('/uploads/online.png').content==original
    assert (tmp_path/'migration-safety/before-v9.sqlite').is_file()


def test_login_rate_limit_and_production(tmp_path):
    with TestClient(create_app(tmp_path,production=True,site_url='https://blog.test'),base_url='https://blog.test',headers={'Origin':'https://blog.test'}) as c:
        assert not c.get('/api/status').json()['setupAllowed']
        assert c.post('/api/setup',json={}).status_code==403
        assert c.post('/api/login',json={},headers={'Origin':'http://blog.test'}).status_code==403
        for _ in range(20): assert c.post('/api/login',json={'password':'wrong'}).status_code==401
        assert c.post('/api/login',json={'password':'wrong'}).status_code==429


def test_git_singleflight_persistence_and_backoff(tmp_path):
    async def scenario():
        store=Store(tmp_path); store.initialize(); calls=[]
        async def upstream(req):
            calls.append(req); await asyncio.sleep(.05)
            return httpx.Response(200,json=[{'created_at':datetime.now(timezone.utc).isoformat()}],headers={'ETag':'"one"'})
        service=GitActivity(store,httpx.MockTransport(upstream))
        started=time.perf_counter()
        for _ in range(30): service.read('github','lin')
        assert time.perf_counter()-started<1
        await asyncio.gather(*service.tasks); assert len(calls)==1
        other=GitActivity(store,httpx.MockTransport(upstream))
        assert other.read('github','lin')['total']==1 and not other.tasks
        with store.connect() as db: db.execute('UPDATE git_cache SET next_attempt=0')
        async def limited(req):
            assert req.headers['If-None-Match']=='"one"'; calls.append(req)
            return httpx.Response(429,headers={'Retry-After':'7200'})
        other.transport=httpx.MockTransport(limited); other.read('github','lin'); await asyncio.gather(*other.tasks)
        for _ in range(10): assert other.read('github','lin')['total']==1
        assert len(calls)==2
        with store.connect() as db: assert db.execute('SELECT next_attempt FROM git_cache').fetchone()[0]>millis()+7100000
    asyncio.run(scenario())


def test_password_rotation_and_session_revocation(client):
    old=client.cookies.get('space_session')
    r=client.post('/api/private/password',json={'old':'test-password-123','password':'new-secure-password'})
    assert r.status_code==200
    fresh=client.cookies.get('space_session'); assert fresh!=old
    client.cookies.clear(); client.cookies.set('space_session',old)
    assert client.get('/api/private/state').status_code==401
    assert client.post('/api/login',json={'password':'test-password-123'}).status_code==401
    assert client.post('/api/login',json={'password':'new-secure-password'}).status_code==200


def test_single_use_captcha_and_approval(client):
    challenge=client.get('/api/register/captcha').json()
    with client.app.state.store.connect() as db:
        db.execute('UPDATE captchas SET answer=? WHERE id=?',(sha(challenge['id']+':12345'),challenge['id']))
    b={'username':'newreader','name':'Reader','password':'reader-password','reason':'To comment','captchaId':challenge['id'],'captchaAnswer':'wrong'}
    assert client.post('/api/register',json=b).status_code==400
    assert client.post('/api/register',json={**b,'captchaAnswer':'12345'}).status_code==400
    challenge=client.get('/api/register/captcha').json()
    with client.app.state.store.connect() as db: db.execute('UPDATE captchas SET answer=? WHERE id=?',(sha(challenge['id']+':12345'),challenge['id']))
    assert client.post('/api/register',json={**b,'captchaId':challenge['id'],'captchaAnswer':'12345'}).status_code==202
    assert client.post('/api/login',json={'username':'newreader','password':'reader-password'}).status_code==401
    registration=client.get('/api/admin/registrations').json()[0]
    assert 'hash' not in registration and 'salt' not in registration
    assert client.put('/api/admin/registrations/'+registration['id'],json={'status':'approved'}).status_code==200
    with client.app.state.store.connect() as db: assert db.execute('SELECT hash FROM registrations WHERE id=?',(registration['id'],)).fetchone()[0]==''
    assert client.post('/api/login',json={'username':'newreader','password':'reader-password'}).status_code==200
    assert client.get('/api/status').json()['user']['role']=='member'


def test_forged_proxy_header_does_not_reset_login_limit(tmp_path):
    with TestClient(create_app(tmp_path),headers={'Origin':'http://testserver'}) as c:
        for n in range(20): assert c.post('/api/login',json={'password':'wrong'},headers={'X-Forwarded-For':f'10.0.0.{n}'}).status_code==401
        assert c.post('/api/login',json={'password':'wrong'},headers={'X-Forwarded-For':'1.2.3.4'}).status_code==429


def test_bounded_body_and_strict_image_decoding(client):
    r=client.post('/api/studio/preview',content=b'x'*(12*1024*1024+1),headers={'Content-Type':'application/json'})
    assert r.status_code==413
    broken='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jvRkAAAAASUVORK5CYII='
    assert client.post('/api/studio/upload',json={'data':broken}).status_code==400
    assert client.post('/api/studio/posts',json=post(cover='/uploads/../../secret.png')).status_code==400
    assert client.post('/api/studio/posts',json=post(origin_url='javascript:alert(1)')).status_code==400
    assert client.post('/api/studio/preview',json={'content':'[x](data:text/html;base64,AAAA)'}).json()['html'].find('href="data:')==-1


def test_story_focus_and_sleep_constraints(client):
    with client.app.state.store.connect() as db:
        s=meta(db,'story');s['points']=90;s['lastClick']=0;set_meta(db,'story',s)
    assert client.post('/api/private/story/click').json()['phase']=='transition'
    assert client.post('/api/private/story/finish').json()['round']==2
    assert client.post('/api/private/focus',json={'action':'start','minutes':25}).status_code==200
    assert client.post('/api/private/focus',json={'action':'start'}).status_code==409
    assert client.post('/api/private/focus',json={'action':'pause'}).json()['endAt'] is None
    assert client.post('/api/private/focus',json={'action':'resume'}).json()['endAt']>millis()
    with client.app.state.store.connect() as db:
        f=meta(db,'focus');f['endAt']=millis()-1;set_meta(db,'focus',f)
    state=client.get('/api/private/state').json()
    assert state['focus'] is None and state['sessions'][0]['minutes']==25
    sleep=state['records']['sleep'][0]
    assert client.put('/api/private/records/sleep/'+sleep['id'],json={**sleep,'deep':0,'light':0,'rem':0,'awake':0}).status_code==400


def test_concurrent_version_updates_have_one_winner(client):
    row=client.post('/api/studio/posts',json=post()).json()
    def update(n): return client.put('/api/studio/posts/'+row['id'],json={**row,'title':str(n)}).status_code
    with ThreadPoolExecutor(max_workers=4) as pool: statuses=list(pool.map(update,range(4)))
    assert statuses.count(200)==1 and statuses.count(409)==3


def test_git_etag_timeouts_and_provider_isolation(tmp_path):
    async def scenario():
        store=Store(tmp_path);store.initialize(); calls=[]
        async def upstream(req):
            calls.append(req)
            assert req.url.host=='gitee.com' and 'Authorization' not in req.headers
            return httpx.Response(200,json=[],headers={'ETag':'"cache"'})
        service=GitActivity(store,httpx.MockTransport(upstream)); service.read('gitee','user'); await asyncio.gather(*service.tasks)
        with store.connect() as db: db.execute('UPDATE git_cache SET next_attempt=0')
        async def unchanged(req):
            assert req.headers['If-None-Match']=='"cache"';return httpx.Response(304)
        service.transport=httpx.MockTransport(unchanged);service.read('gitee','user');await asyncio.gather(*service.tasks)
        with store.connect() as db: db.execute('UPDATE git_cache SET next_attempt=0')
        async def timeout(req): raise httpx.ReadTimeout('simulated')
        service.transport=httpx.MockTransport(timeout);service.read('gitee','user');await asyncio.gather(*service.tasks)
        result=service.read('gitee','user');assert result['updatedAt'] and '暂时' in result['message']
        assert not service.tasks
        with pytest.raises(ValueError): service.read('github','../../etc/passwd')
        await service.close()
    asyncio.run(scenario())
