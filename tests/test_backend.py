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


def test_public_site_status_and_start_date(client):
    settings=client.get('/api/admin/site').json()
    settings['siteStartedAt']='2026-09-14T00:00:00+08:00'
    assert client.put('/api/admin/site',json=settings).status_code==200
    for invalid in [None,False,'not-a-date','2026-09-14T00:00:00']:
        assert client.put('/api/admin/site',json={**settings,'siteStartedAt':invalid}).status_code==400
    client.cookies.clear()
    response=client.get('/api/public/status')
    assert response.status_code==200
    assert set(response.json())=={'ok','version','siteStartedAt','checkedAt'}
    assert response.json()['siteStartedAt']==settings['siteStartedAt']
    assert response.headers['cache-control']=='no-store'
    for path in ('/fonts/inter-latin.woff2','/fonts/lora-latin.woff2'):
        font=client.get(path)
        assert font.status_code==200 and font.content.startswith(b'wOF2')
    assert client.get('/fonts/Inter-OFL.txt').status_code==200
    assert client.get('/fonts/Lora-OFL.txt').status_code==200
    assert client.get('/fonts/manifest.json').status_code==404


def test_admin_build_assets_cache_without_session_lookup(client,monkeypatch):
    from backend import main
    entry=main.ROOT/'public/admin-app/index.html'
    import re
    assets=re.findall(r'(?:src|href)="(/admin-app/assets/[^"?]+)"',entry.read_text(encoding='utf-8'))
    assert assets,'Build the admin frontend before running this test'
    def unexpected(*args):raise AssertionError('Public build asset must not resolve a session')
    with monkeypatch.context() as patch:
        patch.setattr(main,'identity',unexpected)
        for path in assets:
            response=client.get(path)
            assert response.status_code==200
            assert response.headers['cache-control']=='public,max-age=31536000,immutable'
    assert client.get('/admin/room').headers['cache-control']=='no-store'
    assert client.get('/api/status').headers['cache-control']=='no-store'
    client.cookies.clear()
    assert client.get('/api/private/state').status_code==401


def post(**kwargs):
    return {'title':'Test','slug':'test-post','excerpt':'Summary','content':'## Hello\n\nText','category':'技术笔记','status':'published','publishAt':datetime.now(timezone.utc).isoformat(),**kwargs}


def png():
    buf=io.BytesIO(); Image.new('RGB',(2,2),'blue').save(buf,format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode()


def test_frontend_read_models_privacy_and_pagination(client):
    assert client.post('/api/studio/posts',json=post(title='Public card',content='PUBLIC BODY NOT IN SUMMARY')).status_code==201
    assert client.post('/api/studio/posts',json=post(title='Private card',slug='private-card',status='private')).status_code==201
    assert client.post('/api/studio/posts',json=post(title='Future card',slug='future-card',status='scheduled',publishAt='2099-01-01T00:00:00Z')).status_code==201
    page=client.get('/api/public/catalog/posts?q=card&pageSize=1').json()
    assert page['total']==1 and page['items'][0]['title']=='Public card'
    assert 'content' not in page['items'][0]
    assert 'PUBLIC BODY NOT IN SUMMARY' not in client.get('/api/public/bootstrap').text
    docs=client.get('/api/private/reference-docs').json()
    bookmarks=[{**docs['items'][0],'public':False},{**docs['items'][1],'public':True}]
    assert client.put('/api/private/reference-docs',json={'version':docs['version'],'items':bookmarks}).status_code==200
    layout=client.get('/api/private/page-layout').json()
    for item in layout['home']:item['enabled']=item['id'] in ('articles','web','anime')
    layout.update(animeSeason='2026-Q4',animeLimit=6,webDocumentId='fastapi')
    assert client.put('/api/private/page-layout',json=layout).status_code==200
    assert client.put('/api/private/page-layout',json={**layout,'animeLimit':True}).status_code==400
    doc=client.post('/api/private/documents',json={'title':'Hidden manual','category':'Test','content':'PRIVATE SENTINEL'}).json()
    listing=client.get('/api/private/catalog/documents?q=Hidden&pageSize=1').json()
    assert listing['total']==1 and listing['items'][0]['id']==doc['id']
    assert 'content' not in listing['items'][0]
    assert client.get('/api/private/documents/'+doc['id']).json()['content']=='PRIVATE SENTINEL'
    assert client.get('/api/private/documents/missing').status_code==404
    assert client.get('/api/private/overview').json()['content']['documents']==1
    contract=client.get('/api/private/api-contract').json()
    assert '/api/public/home' in contract['openapi']['paths']
    assert contract['recordSchemas']
    media=client.get('/api/private/media?pageSize=1').json()
    assert len(media['items'])<=1 and media['pageSize']==1
    assert client.get('/api/private/media?source=invalid').status_code==400
    assert client.get('/api/private/catalog/records/library?pageSize=1').status_code==200
    assert client.get('/api/public/catalog/anime?pageSize=101').status_code==400
    assert client.get('/api/public/catalog/anime?season=2026-Q9').status_code==400
    assert client.get('/api/public/catalog/anime?weekday=八').status_code==400
    client.cookies.clear()
    home=client.get('/api/public/home').json()
    web=next(row['data'] for row in home['modules'] if row['id']=='web')
    assert [row['id'] for row in web['items']]==['fastapi']
    assert web['selected']['embeddable'] is True
    initial=client.get('/api/public/bootstrap').json()
    assert 'room' not in initial['layout'] and initial['apiVersion']=='1'
    assert 'PRIVATE SENTINEL' not in json.dumps(home)
    for path in ['/api/private/overview','/api/private/catalog/documents','/api/private/api-contract','/api/private/media','/api/private/automation/runs']:
        assert client.get(path).status_code==401


def test_automation_summaries_and_details(client):
    flow=client.post('/api/private/automation/flows',json={'name':'Read model','template':'local-digest'}).json()
    token=client.post('/api/private/access-tokens',json={'name':'Read model','scopes':['automation:submit']}).json()['token']
    run=client.post('/api/v1/automation/results',headers={'Authorization':'Bearer '+token,'Idempotency-Key':'read-model'},json={'flowId':flow['id'],'title':'Long result','content':'Result body '*1000})
    assert run.status_code==201,run.text
    overview=client.get('/api/private/automation?compact=true').json()
    summary=overview['runs'][0]
    assert summary['name']=='Read model' and 'result' not in summary and 'snapshot' not in summary
    page=client.get('/api/private/automation/runs?pageSize=1&state=waiting_approval').json()
    assert page['total']==1 and len(page['items'])==1
    detail=client.get('/api/private/automation/runs/'+summary['id']).json()
    assert 'Result body' in detail['result']['text']
    assert client.get('/api/private/automation/runs?state=invalid').status_code==400
    assert client.get('/api/private/automation/runs/missing').status_code==404


def test_journal_image_formats_preserve_visibility(client, tmp_path):
    uploads=tmp_path/'uploads'
    uploads.mkdir(exist_ok=True)
    for name in ('old.png','new.png','private.png','other.png'):
        Image.new('RGB',(2,2),'blue').save(uploads/name)
    with client.app.state.store.transaction() as db:
        for ident,status,images in [('old','published',['/uploads/old.png']),('new','published',[{'url':'/uploads/new.png'}]),('private','draft',['/uploads/private.png'])]:
            db.execute("INSERT INTO journal VALUES(?, 'moments', 'owner', ?, 1, '2026-01-01', '2026-01-01')",(ident,dumps({'status':status,'images':images})))
    assert client.get('/uploads/other.png').status_code==200
    client.cookies.clear()
    assert client.get('/uploads/old.png').status_code==200
    assert client.get('/uploads/new.png').status_code==200
    assert client.get('/uploads/private.png').status_code in (401,403,404)
    assert client.get('/uploads/other.png').status_code in (401,403,404)


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


def test_private_documents_versions_and_access(client):
    created=client.post('/api/private/documents',json={'title':'Release map','category':'Engineering','content':'```mermaid\nflowchart LR\n A-->B\n```'})
    assert created.status_code==201,created.text
    row=created.json(); assert row['version']==1 and row['content'].startswith('```mermaid')
    assert client.get('/api/private/documents').json()[0]['id']==row['id']
    updated=client.put('/api/private/documents/'+row['id'],json={**row,'title':'Release plan'})
    assert updated.status_code==200 and updated.json()['version']==2
    assert client.put('/api/private/documents/'+row['id'],json=row).status_code==409
    assert client.request('DELETE','/api/private/documents/'+row['id'],json={'version':1}).status_code==409
    assert client.request('DELETE','/api/private/documents/'+row['id'],json={'version':2}).status_code==200
    assert client.get('/api/private/documents').json()==[]
    assert client.post('/api/admin/users',json={'username':'docreader','name':'Reader','password':'reader-password'}).status_code==201
    cookie=client.cookies.get('space_session');client.cookies.clear()
    assert client.get('/api/private/documents').status_code==401
    client.cookies.set('space_session',cookie)
    assert client.post('/api/private/documents',json={'title':'x'}).status_code==201
    client.cookies.clear();assert client.post('/api/login',json={'username':'docreader','password':'reader-password'}).status_code==200
    assert client.get('/api/private/documents').status_code==403


def test_automation_queue_approval_idempotency_and_cancel(client,monkeypatch):
    import backend.automation as a
    flow=client.post('/api/private/automation/flows',json={'name':'Season','template':'seasonal-anime','config':{'saveLibrary':True}}).json()
    assert flow['version']==1
    row=client.post(f'/api/private/automation/flows/{flow["id"]}/run',json={'key':'one'}).json()
    assert client.post(f'/api/private/automation/flows/{flow["id"]}/run',json={'key':'one'}).json()['id']==row['id']
    assert client.post(f'/api/private/automation/runs/{row["id"]}/approve').status_code==409
    monkeypatch.setattr(a,'collect',lambda *args:{'title':'Season','text':'Source report','items':[{'sourceKey':'yuc:test:01','title':'Show','url':'https://yuc.wiki/202610/','broadcast':'10/1','tags':'Test','cover':''}],'warnings':[]})
    a.process_one(client.app.state.store)
    before=len(client.get('/api/private/state').json()['records']['library'])
    approved=client.post(f'/api/private/automation/runs/{row["id"]}/approve').json()
    assert approved['state']=='succeeded' and approved['result']['added']==1
    assert client.post(f'/api/private/automation/runs/{row["id"]}/approve').json()['state']=='succeeded'
    assert len(client.get('/api/private/state').json()['records']['library'])==before+1
    second=client.post(f'/api/private/automation/flows/{flow["id"]}/run',json={'key':'two'}).json();a.process_one(client.app.state.store)
    assert client.post(f'/api/private/automation/runs/{second["id"]}/approve').json()['result']['added']==0
    third=client.post(f'/api/private/automation/flows/{flow["id"]}/run',json={'key':'three'}).json()
    assert client.post(f'/api/private/automation/runs/{third["id"]}/cancel').status_code==200
    assert client.post(f'/api/private/automation/runs/{third["id"]}/approve').status_code==409
    assert client.put('/api/private/automation/pause',json={'paused':True}).status_code==200
    assert client.post(f'/api/private/automation/flows/{flow["id"]}/run',json={'key':'four'}).status_code==409
    assert client.put('/api/private/automation/flows/'+flow['id'],json={**flow,'version':0}).status_code==409


def test_automation_delete_preserves_runs_and_checks_version(client):
    flow=client.post('/api/private/automation/flows',json={'name':'Remove','template':'seasonal-anime'}).json()
    assert flow['config']['limit']==0
    run=client.post('/api/private/automation/flows/'+flow['id']+'/run',json={'key':'delete-test'}).json()
    url='/api/private/automation/flows/'+flow['id']
    assert client.request('DELETE',url,json={'version':0}).status_code==409
    assert client.request('DELETE',url,json={'version':1}).status_code==409
    assert client.post('/api/private/automation/runs/'+run['id']+'/cancel').status_code==200
    assert client.request('DELETE',url,json={'version':1}).status_code==200
    result=client.get('/api/private/automation').json()
    assert not any(f['id']==flow['id'] for f in result['flows'])
    assert any(r['id']==run['id'] for r in result['runs'])


def test_seasonal_parser_ssrf_redirect_limits_and_structure():
    from backend.automation import parse_season,allowed_url,bounded_fetch
    fixture='<!--#A01--><div><img data-src="https://i0.hdslb.com/bfs/test.jpg"></div><p class="title_cn_r1">Test &amp; Name</p><p class="title_jp_r">Original</p><p class="broadcast_r">10/1</p><!--#A02--><p class="title_cn_r">Second</p>'
    rows=parse_season(fixture,'202610');assert len(rows)==2 and rows[0]['title']=='Test & Name' and rows[0]['broadcast']=='10/1'
    with pytest.raises(ValueError):parse_season('<p>changed</p>','202610')
    for url in ['http://yuc.wiki/202610/','https://127.0.0.1/202610/','https://yuc.wiki.evil.test/202610/','https://yuc.wiki@evil.test/202610/','https://yuc.wiki/202610/?url=internal','https://yuc.wiki:123/202610/']:
        with pytest.raises(ValueError):allowed_url(url)
    with pytest.raises(ValueError):allowed_url('https://i0.hdslb.com/anything',True)
    with pytest.raises(httpx.HTTPStatusError):bounded_fetch('https://yuc.wiki/202610/',100,transport=httpx.MockTransport(lambda r:httpx.Response(302,headers={'location':'http://127.0.0.1'})))
    with pytest.raises(ValueError):bounded_fetch('https://yuc.wiki/202610/',20,transport=httpx.MockTransport(lambda r:httpx.Response(200,headers={'content-type':'text/html'},content=b'a'*100)))


def test_automation_schedule_lease_recovery_and_failed_source(client,monkeypatch):
    import backend.automation as a
    flow=client.post('/api/private/automation/flows',json={'name':'Weekly','template':'weekly-review','config':{'schedule':'weekly','weekday':0,'sendTime':'08:00'}}).json()
    enabled=client.put('/api/private/automation/flows/'+flow['id'],json={**flow,'enabled':True}).json()
    now=datetime(2026,11,9,9,tzinfo=timezone.utc)
    a.schedule_tick(client.app.state.store,now);a.schedule_tick(client.app.state.store,now)
    runs=client.get('/api/private/automation').json()['runs'];assert len(runs)==1
    with client.app.state.store.transaction() as db:db.execute("UPDATE automation_runs SET state='running',leaseUntil=0,attempts=1")
    a.process_one(client.app.state.store)
    assert client.get('/api/private/automation').json()['runs'][0]['state']=='waiting_approval'
    flow=client.post('/api/private/automation/flows',json={'name':'Fail','template':'weekly-review'}).json()
    row=client.post('/api/private/automation/flows/'+flow['id']+'/run',json={'key':'bad'}).json()
    def broken(*args):raise TimeoutError('private upstream secret')
    monkeypatch.setattr(a,'collect',broken);a.process_one(client.app.state.store)
    result=client.get('/api/private/automation').json()['runs'][0]
    assert result['state']=='failed' and 'private upstream secret' not in result['error']


def test_local_ai_result_scopes_idempotency_and_private_output(client):
    flow=client.post('/api/private/automation/flows',json={'name':'Local','template':'local-digest'}).json()
    token=client.post('/api/private/access-tokens',json={'name':'Local executor','scopes':['automation:submit']}).json()['token']
    headers={'Authorization':'Bearer '+token,'Idempotency-Key':'one','Origin':'https://local-agent.test'}
    body={'flowId':flow['id'],'title':'Local report','content':'Private result'}
    assert client.post('/api/v1/automation/results',json=body).status_code==401
    row=client.post('/api/v1/automation/results',json=body,headers=headers);assert row.status_code==201,row.text
    assert row.json()['state']=='waiting_approval'
    assert client.post('/api/v1/automation/results',json=body,headers=headers).json()['id']==row.json()['id']
    assert client.post('/api/v1/automation/results',json={**body,'content':'changed'},headers=headers).status_code==409
    assert client.post('/api/v1/posts',json={'title':'Not allowed'},headers=headers).status_code==403
    before=len(client.get('/api/private/documents').json())
    assert client.post('/api/private/automation/runs/'+row.json()['id']+'/approve').status_code==200
    assert len(client.get('/api/private/documents').json())==before+1


def test_layout_reference_docs_import_and_public_isolation(client):
    layout=client.get('/api/private/page-layout').json();layout['home'].reverse();layout['accent']='forest'
    updated=client.put('/api/private/page-layout',json=layout);assert updated.status_code==200,updated.text
    assert 'room' not in client.get('/api/page-layout').json()
    assert client.put('/api/private/page-layout',json=layout).status_code==409
    broken={**updated.json(),'room':updated.json()['room']*2}
    assert client.put('/api/private/page-layout',json=broken).status_code==400
    docs=client.get('/api/private/reference-docs').json()
    assert next(d for d in docs['items'] if d['id']=='mdn')['embeddable'] is False
    assert next(d for d in docs['items'] if d['id']=='fastapi')['embeddable'] is True
    assert client.put('/api/private/reference-docs',json={'version':docs['version'],'items':[{'id':'bad','title':'bad','url':'javascript:alert(1)'}]}).status_code==400
    assert client.post('/api/private/reference-docs/visit',json={'id':'vue'}).status_code==200
    assert client.get('/api/private/reference-docs').json()['recent']==['vue']
    payload={'posts':[{'title':'UI imported','slug':'ui-imported','content':'hello'}]}
    assert client.post('/api/private/imports/validate',json=payload).json()['valid']
    assert client.post('/api/private/imports',json=payload).status_code==201
    client.cookies.clear()
    for path in ['/api/private/automation','/api/private/reference-docs','/api/private/page-layout']:
        assert client.get(path).status_code==401


def test_anime_wall_and_intro_photo_publication_boundary(client):
    from backend.validation import validate_record
    from backend.content import insert
    cover=client.post('/api/studio/upload',json={'data':png()}).json()['url']
    with client.app.state.store.transaction() as db:
        insert(db,'library',validate_record('library',{'title':'Private Anime','kind':'番剧','status':'wish','progress':0,'total':12,'cover':cover,'note':'private','tags':'test'}))
    # The collection remains private, and its image stays private until explicitly selected.
    client.cookies.clear()
    assert client.get('/api/private/state').status_code==401
    assert client.get(cover).status_code==404
    assert 'library' not in client.get('/api/page-layout').json()
    client.post('/api/login',json={'username':'admin','password':'test-password-123'})
    layout=client.get('/api/private/page-layout').json()
    layout.update(introPhotoMode='custom',introPhotos=[cover])
    assert client.put('/api/private/page-layout',json=layout).status_code==200
    public=client.get('/api/page-layout').json()
    assert public['introPhotoMode']=='custom' and public['introPhotos']==[cover]
    client.cookies.clear()
    assert client.get(cover).status_code==200
    assert client.get('/api/private/state').status_code==401
    client.post('/api/login',json={'username':'admin','password':'test-password-123'})
    layout=client.get('/api/private/page-layout').json()
    invalid={**layout,'introPhotos':['https://example.test/poster.jpg']}
    assert client.put('/api/private/page-layout',json=invalid).status_code==400
    excessive={**layout,'introPhotos':['/uploads/pic-'+str(i)+'.webp' for i in range(19)]}
    assert client.put('/api/private/page-layout',json=excessive).status_code==400


def test_public_anime_seasons_and_private_fields(client):
    cover=client.post('/api/studio/upload',json={'data':png()}).json()['url']
    body={'title':'Season Anime','kind':'番剧','status':'wish','progress':0,'total':12,'cover':cover,'season':'2026-Q4','broadcast':'10月','public':True,'note':'private thoughts'}
    row=client.post('/api/private/records/library',json=body).json()
    assert row['season']=='2026-Q4' and row['public'] is True
    assert client.post('/api/private/records/library',json={**body,'season':'2026-Q5'}).status_code==400
    cookie=client.cookies.get('space_session');client.cookies.clear()
    result=client.get('/api/public/anime?season=2026-Q4').json()
    assert result['seasons']==['2026-Q4']
    assert len(result['items'])==1 and 'note' not in result['items'][0] and 'progress' not in result['items'][0]
    assert client.get('/api/public/anime?season=2026-Q3').json()['items']==[]
    assert client.get('/api/public/anime?season=bad').status_code==400
    assert client.get(cover).status_code==200
    client.cookies.set('space_session',cookie)
    assert client.put('/api/private/records/library/'+row['id'],json={**row,'public':False}).status_code==200
    client.cookies.clear()
    assert client.get('/api/public/anime').json()['items']==[]
    assert client.get(cover).status_code==404


def test_imported_anime_public_switch_preserves_private_collections(client):
    cover=client.post('/api/studio/upload',json={'data':png()}).json()['url']
    body={'title':'Imported Anime','kind':'番剧','status':'wish','progress':0,'total':12,'cover':cover,'season':'2026-Q4','public':False,'note':'private thoughts'}
    imported=client.post('/api/private/records/library',json=body).json()
    client.post('/api/private/records/library',json={**body,'title':'Manual Private'})
    with client.app.state.store.transaction() as db:
        db.execute('INSERT INTO automation_items VALUES(?,?,?)',('yuc:202610:A01',imported['id'],'2026-10-01'))
    client.cookies.clear()
    result=client.get('/api/public/anime').json()['items']
    assert [item['title'] for item in result]==['Imported Anime']
    assert 'note' not in result[0] and 'progress' not in result[0]
    assert client.get(cover).status_code==200
    client.post('/api/login',json={'username':'admin','password':'test-password-123'})
    layout=client.get('/api/private/page-layout').json();layout['animeAutoPublic']=False
    assert client.put('/api/private/page-layout',json=layout).status_code==200
    client.cookies.clear()
    assert client.get('/api/public/anime').json()['items']==[]
    assert client.get(cover).status_code==404


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
    document=client.post('/api/private/documents',json={'title':'Keep me','category':'Work','content':'A private note'}).json()
    backup=client.get('/api/private/backup').json()
    assert backup['documents'][0]['id']==document['id']
    assert client.post('/api/private/restore',json=backup).status_code==200
    assert client.get('/api/private/documents').json()[0]['content']=='A private note'
    old_backup={k:v for k,v in backup.items() if k!='documents'}
    assert client.post('/api/private/restore',json=old_backup).status_code==200
    assert client.get('/api/private/documents').json()[0]['id']==document['id']
    assert client.post('/api/private/restore',json={**backup,'records':backup['records']+[backup['records'][0]]}).status_code==400
    assert client.post('/api/private/restore',json={**backup,'documents':backup['documents']*2}).status_code==400
    assert client.get('/api/status').json()['authenticated']


def test_scoped_access_tokens_content_api_and_json_import(client):
    assert client.post('/api/v1/posts',json={'title':'Cookie only','slug':'cookie-only','content':'no bearer','category':'技术笔记'},headers={'Idempotency-Key':'cookie-only'}).status_code==401
    created=client.post('/api/private/access-tokens',json={'name':'Local AI'}); assert created.status_code==200,created.text
    token=created.json()['token']; identifier=created.json()['id']
    assert token.startswith('sk-')
    headers={'Authorization':'Bearer '+token,'Idempotency-Key':'local-ai-post-1','Origin':'https://external-ai.test'}
    draft={'title':'AI draft','slug':'ai-draft','content':'Draft from local AI','category':'技术笔记'}
    first=client.post('/api/v1/posts',json=draft,headers=headers); assert first.status_code==201,first.text
    assert first.json()['status']=='draft' and not first.json()['replayed']
    replay=client.post('/api/v1/posts',json=draft,headers=headers); assert replay.status_code==201,replay.text; assert replay.json()['replayed']
    assert client.post('/api/v1/posts',json={**draft,'title':'Changed'},headers=headers).status_code==409
    assert client.post('/api/v1/posts',json={**draft,'slug':'needs-publish','requestedState':'published'},headers={**headers,'Idempotency-Key':'publish-1'}).status_code==403

    import_token=client.post('/api/private/access-tokens',json={'name':'JSON import','scopes':['content:import']}).json()['token']
    import_headers={'Authorization':'Bearer '+import_token}
    payload={'posts':[{'title':'Imported note','slug':'imported-note','content':'Imported body','category':'日常手记'}]}
    assert client.post('/api/v1/imports/validate',json=payload,headers=import_headers).json()=={'valid':True,'count':1,'errors':[]}
    result=client.post('/api/v1/imports',json=payload,headers=import_headers); assert result.status_code==201,result.text
    assert result.json()['created'][0]['slug']=='imported-note'
    duplicate={'posts':[payload['posts'][0],{**payload['posts'][0],'title':'duplicate'}]}
    assert client.post('/api/v1/imports',json=duplicate,headers=import_headers).status_code==409

    assert client.delete('/api/private/access-tokens/'+identifier).status_code==200
    assert client.post('/api/v1/posts',json={**draft,'slug':'revoked-token'},headers={**headers,'Idempotency-Key':'revoked'}).status_code==401


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


def test_mail_settings_encrypt_secrets_preview_and_delivery(client,monkeypatch):
    from cryptography.fernet import Fernet
    import backend.mailing as mailing
    monkeypatch.setenv('EMAIL_ENCRYPTION_KEY',Fernet.generate_key().decode())
    sent=[]
    monkeypatch.setattr(mailing,'test_connection',lambda config:None)
    monkeypatch.setattr(mailing,'send_email',lambda config,subject,body,recipient=None:sent.append((subject,body,recipient,config)))
    config={'host':'smtp.example.test','port':587,'sender':'site@example.test','recipient':'owner@example.test','username':'site@example.test','password':'app-secret','useTls':True,'timezone':'Asia/Shanghai','enabled':False,'weekday':1,'sendTime':'09:00'}
    saved=client.put('/api/private/mail/settings',json=config)
    assert saved.status_code==200,saved.text
    assert saved.json()['passwordConfigured'] is True and 'password' not in saved.json()
    with client.app.state.store.connect() as db:
        encrypted=meta(db,'mailSettings')['password']
        assert encrypted!='app-secret' and mailing._credentials(meta(db,'mailSettings'))=='app-secret'
    assert client.post('/api/private/mail/test',json={'recipient':'test@example.test'}).json()['ok'] is True
    preview=client.get('/api/private/mail/preview').json()
    assert preview['posts']==[] and '本周发布 0 篇文章' in preview['text']
    result=client.post('/api/private/mail/send')
    assert result.status_code==200 and result.json()['status']=='succeeded'
    assert sent[-1][3]['recipient']=='owner@example.test'
    assert client.get('/api/private/mail/runs').json()[0]['status']=='succeeded'


def test_mail_configuration_errors_are_actionable_and_connections_are_closed(monkeypatch):
    import smtplib
    import backend.mailing as mailing
    assert '授权码' in mailing.connection_error(smtplib.SMTPAuthenticationError(535,b'private provider detail'))
    assert '587' in mailing.connection_error(smtplib.SMTPNotSupportedError('private provider detail'))
    closed=[]
    class BrokenSMTP:
        def __init__(self,*args,**kwargs): pass
        def ehlo(self): pass
        def starttls(self): raise smtplib.SMTPNotSupportedError('provider text')
        def close(self): closed.append(True)
    monkeypatch.setattr(mailing.smtplib,'SMTP',BrokenSMTP)
    monkeypatch.setattr(mailing,'_credentials',lambda config:'secret')
    with pytest.raises(smtplib.SMTPNotSupportedError):
        mailing._connect({'host':'smtp.example.test','port':587,'useTls':True})
    assert closed==[True]


def test_mail_secret_requires_deployment_encryption_key(client,monkeypatch):
    monkeypatch.delenv('EMAIL_ENCRYPTION_KEY',raising=False)
    config={'host':'smtp.example.test','port':587,'sender':'site@example.test','recipient':'owner@example.test','username':'site@example.test','password':'private-app-code','useTls':True,'timezone':'Asia/Shanghai','enabled':False,'weekday':1,'sendTime':'09:00'}
    response=client.put('/api/private/mail/settings',json=config)
    assert response.status_code==400
    assert 'EMAIL_ENCRYPTION_KEY' in response.json()['error']
    assert 'private-app-code' not in response.text


def test_mail_test_reports_safe_smtp_diagnostic(client,monkeypatch):
    from cryptography.fernet import Fernet
    import smtplib
    import backend.mailing as mailing
    monkeypatch.setenv('EMAIL_ENCRYPTION_KEY',Fernet.generate_key().decode())
    config={'host':'smtp.example.test','port':587,'sender':'site@example.test','recipient':'owner@example.test','username':'site@example.test','password':'private-app-code','useTls':True,'timezone':'Asia/Shanghai','enabled':False,'weekday':1,'sendTime':'09:00'}
    assert client.put('/api/private/mail/settings',json=config).status_code==200
    def rejected(*args,**kwargs): raise smtplib.SMTPAuthenticationError(535,b'secret provider response')
    monkeypatch.setattr(mailing,'send_email',rejected)
    response=client.post('/api/private/mail/test',json={})
    assert response.status_code==502
    assert '授权码' in response.json()['error']
    assert 'secret provider response' not in response.text and 'private-app-code' not in response.text


def test_mail_automatic_schedule_requires_secret_and_deduplicates(client,monkeypatch):
    from cryptography.fernet import Fernet
    import backend.mailing as mailing
    import backend.api as api
    monkeypatch.setenv('EMAIL_ENCRYPTION_KEY',Fernet.generate_key().decode())
    config={'host':'smtp.example.test','port':587,'sender':'site@example.test','recipient':'owner@example.test','username':'site@example.test','password':'app-secret','useTls':True,'timezone':'Asia/Shanghai','enabled':True,'weekday':1,'sendTime':'09:00'}
    assert client.put('/api/private/mail/settings',json={k:v for k,v in config.items() if k!='password'}).status_code==400
    assert client.put('/api/private/mail/settings',json=config).status_code==200
    calls=[]
    monkeypatch.setattr(mailing,'send_email',lambda *args,**kwargs:calls.append(args))
    app=client.app
    first=api.deliver_report(app,'scheduled','2026-W45')
    second=api.deliver_report(app,'scheduled','2026-W45')
    assert first['status']=='succeeded' and second['status']=='duplicate'
    assert len(calls)==1


def test_mail_uncertain_delivery_cannot_be_retried(client,monkeypatch):
    from cryptography.fernet import Fernet
    import backend.mailing as mailing
    import backend.api as api
    monkeypatch.setenv('EMAIL_ENCRYPTION_KEY',Fernet.generate_key().decode())
    config={'host':'smtp.example.test','port':587,'sender':'site@example.test','recipient':'owner@example.test','username':'site@example.test','password':'app-secret','useTls':True,'timezone':'Asia/Shanghai','enabled':True,'weekday':1,'sendTime':'09:00'}
    assert client.put('/api/private/mail/settings',json=config).status_code==200
    def uncertain(*args,**kwargs): raise mailing.DeliveryUnknown()
    monkeypatch.setattr(mailing,'send_email',uncertain)
    result=api.deliver_report(client.app,'scheduled','2026-W46')
    assert result['status']=='unknown'
    assert client.post('/api/private/mail/runs/'+result['id']+'/retry',json={}).status_code==409


def test_mail_interrupted_send_recovers_as_unknown(tmp_path):
    from backend.mailing import recover_interrupted
    store=Store(tmp_path);store.initialize()
    with store.transaction() as db:
        db.execute("INSERT INTO email_runs(id,kind,status,subject,recipient,created) VALUES('run','manual','sending','Weekly','owner@example.test',?)",('2026-11-06T00:00:00Z',))
    recover_interrupted(store)
    with store.connect() as db:
        row=db.execute("SELECT status,error FROM email_runs WHERE id='run'").fetchone()
        assert row['status']=='unknown' and '检查收件箱' in row['error']


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
