"""Stable V8 API paths, backed entirely by Python/SQLite."""
import base64
import copy
import json
import logging
import math
import os
import re
import secrets
import sqlite3
from uuid import uuid4
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from .storage import meta, set_meta, stamp, dumps, record, audit
from .validation import *
from .security import *
from .content import profile, site, author, records, public_posts, visible_post, markdown, taxonomy, save, remove, settle_focus, story_action, journal_row, insert, unique, unlock, day

router=APIRouter(prefix='/api')


def store(request): return request.app.state.store
def ip(request): return request.client.host if request.client else 'unknown'
def user(request): return request.state.user


@router.get('/status')
def status(request:Request):
    with store(request).connect() as db:
        return {'setup':not bool(meta(db,'account')),'authenticated':bool(user(request)),'user':user(request),'setupAllowed':not request.app.state.production}


@router.post('/setup')
def setup(request:Request,body:dict):
    if request.app.state.production: fail(403,'生产环境请使用命令行初始化站主')
    with store(request).transaction() as db:
        rate(db,ip(request),'setup',20)
        if meta(db,'account'): fail(409,'账号已经创建')
        name=text(body.get('name'),80,1,True); salt,hashed=credentials(body.get('password'))
        set_meta(db,'account',{'name':name,'salt':salt,'hash':hashed})
        set_meta(db,'profile',{**DEFAULT_PROFILE,'name':name}); set_meta(db,'story',DEFAULT_STORY)
        if body.get('demo') is True:
            for entry in CONTRACT['demo']: insert(db,entry['kind'],validate_record(entry['kind'],entry['data']))
        response=JSONResponse({'ok':True}); session(db,response,'owner',request.app.state.secure)
        return response


@router.post('/login')
def sign_in(request:Request,body:dict):
    with store(request).transaction() as db: rate(db,ip(request),'login',20)
    with store(request).transaction() as db:
        uid=login(db,body.get('username'),body.get('password'))
        response=JSONResponse({'ok':True}); session(db,response,uid,request.app.state.secure)
        return response


@router.post('/logout')
def logout(request:Request):
    if not user(request): fail(401,'请先登录')
    with store(request).transaction() as db: db.execute('DELETE FROM sessions WHERE token=?',(sha(request.cookies.get('space_session','')),))
    response=JSONResponse({'ok':True}); response.delete_cookie('space_session',path='/'); return response


@router.get('/site')
def get_site(request:Request):
    with store(request).connect() as db: return {**site(db),'avatar':author(db,'owner')['authorAvatar']}


@router.get('/public')
def public_index(request:Request):
    with store(request).connect() as db:
        p=meta(db,'profile',DEFAULT_PROFILE)
        posts=[{**{k:v for k,v in p.items() if k!='content'},'searchText':p['content'],'reading':max(1,math.ceil(len(p['content'])/450))} for p in public_posts(db)]
        return {'profile':{k:p.get(k,DEFAULT_PROFILE[k]) for k in ('name','tagline','bio','blogWallpaper')},'posts':posts}


@router.get('/public/anime')
def public_anime(request:Request,season:str=''):
    if season and not re.fullmatch(r'[0-9]{4}-Q[1-4]',season): fail(400,'季度格式应为 YYYY-Q1 至 YYYY-Q4')
    with store(request).connect() as db:
        auto_public=meta(db,'pageLayout',{}).get('animeAutoPublic',True)
        imported={r['recordId'] for r in db.execute('SELECT recordId FROM automation_items')} if auto_public else set()
        rows=[{k:item.get(k,'') for k in ('id','title','season','broadcast','cover','creator','tags')} for item in records(db,'library','owner') if item.get('kind')=='番剧' and (item.get('public') is True or item['id'] in imported)]
        seasons=sorted({r['season'] for r in rows if r['season']},reverse=True)
        return {'items':[r for r in rows if not season or r['season']==season],'seasons':seasons}


@router.get('/public/posts/{slug}')
def public_post(request:Request,slug:str):
    with store(request).connect() as db:
        p=visible_post(db,slug); return {**p,**markdown(p['content'])}


@router.get('/public/posts/{slug}/comments')
def comments(request:Request,slug:str):
    with store(request).connect() as db:
        p=visible_post(db,slug)
        return [dict(r) for r in db.execute("SELECT id,name,content,created FROM comments WHERE postId=? AND status='approved' ORDER BY created LIMIT 200",(p['id'],))]


@router.post('/public/posts/{slug}/comments',status_code=202)
def comment(request:Request,slug:str,body:dict):
    name=text(body.get('name'),40,1,True); content=text(body.get('content'),2000,2,True)
    if body.get('website'): fail(400,'提交未通过检查')
    with store(request).transaction() as db:
        p=visible_post(db,slug)
        if not site(db)['commentsEnabled']: fail(403,'评论暂时关闭')
        rate(db,ip(request),'comment',5)
        db.execute('INSERT INTO comments(id,postId,name,content,created,updated) VALUES(?,?,?,?,?,?)',(str(uuid4()),p['id'],name,content,stamp(),stamp()))
    return {'message':'已收到，审核通过后才会公开展示。'}


@router.get('/register/captcha')
def get_captcha(request:Request):
    with store(request).transaction() as db: return captcha(db,ip(request))


@router.post('/register',status_code=202)
def register(request:Request,body:dict):
    username=text(body.get('username'),32,3)
    if not re.fullmatch('[a-z0-9_-]{3,32}',username): fail(400,'账号格式无效')
    name=text(body.get('name'),80,1,True); reason=text(body.get('reason'),500,2,True)
    text(body.get('password'),200,10)
    with store(request).transaction() as db: rate(db,ip(request),'register',10)
    # Consume even a wrong CAPTCHA; failures must not roll back single-use semantics.
    problem=None
    with store(request).transaction() as db:
        try: check_captcha(db,body,ip(request))
        except Problem as e: problem=e
    if problem: raise problem
    salt,hashed=credentials(body['password'])
    with store(request).transaction() as db:
        if username=='admin' or db.execute('SELECT id FROM users WHERE username=?',(username,)).fetchone() or db.execute("SELECT id FROM registrations WHERE username=? AND status='pending'",(username,)).fetchone(): fail(409,'该账号不可申请，可能已注册或正在审核')
        db.execute('INSERT INTO registrations(id,username,name,salt,hash,reason,created) VALUES(?,?,?,?,?,?,?)',(str(uuid4()),username,name,salt,hashed,reason,stamp()))
    return {'message':'申请已提交。站主审核通过后，才能使用此账号登录。'}


@router.get('/studio/me')
def me(request:Request): return user(request)


@router.get('/studio/profile')
def get_profile(request:Request):
    with store(request).connect() as db: return profile(db,user(request))


@router.put('/studio/profile')
def put_profile(request:Request,body:dict):
    b=member_profile(body); uid=user(request)['id']
    with store(request).transaction() as db:
        check_images(db,b,uid)
        if profile(db,user(request))['version']!=body['version']: fail(409,'个人资料已更新，请刷新后重试')
        db.execute('INSERT INTO member_profiles VALUES(?,?,?) ON CONFLICT(userId) DO UPDATE SET data=excluded.data,version=excluded.version',(uid,dumps(b),body['version']+1))
        if uid=='owner': set_meta(db,'account',{**meta(db,'account'),'name':b['name']})
        else: db.execute('UPDATE users SET name=? WHERE id=?',(b['name'],uid))
        key='profile' if uid=='owner' else 'user:'+uid+':profile'
        old=meta(db,key)
        if old:
            set_meta(db,key,{**old,'name':b['name']}); set_meta(db,key+'Version',meta(db,key+'Version',1)+1)
        return profile(db,{**user(request),'name':b['name']})


@router.get('/studio/git')
async def git(request:Request):
    with store(request).connect() as db: p=profile(db,user(request))
    return request.app.state.git.read(p['gitProvider'],p['gitUsername'])


@router.post('/private/upload')
@router.post('/studio/upload')
def upload(request:Request,body:dict):
    with store(request).transaction() as db: rate(db,ip(request),'upload',60)
    raw,extension=image_bytes(body.get('data')); name=str(uuid4())+'.'+extension
    dest=store(request).directory/'uploads'/name
    try:
        dest.write_bytes(raw)
        with store(request).transaction() as db: db.execute('INSERT INTO upload_owners VALUES(?,?)',(name,user(request)['id']))
    except BaseException:
        dest.unlink(missing_ok=True); raise
    return {'url':'/uploads/'+name}


@router.get('/studio/posts')
def get_posts(request:Request):
    with store(request).connect() as db:
        return [{**record(r),'authorId':r['userId']} for r in db.execute("SELECT * FROM records WHERE kind='posts' AND deleted IS NULL ORDER BY created DESC,id")]


@router.post('/studio/posts',status_code=201)
def create_post(request:Request,body:dict):
    with store(request).transaction() as db: return save(db,'posts',body)


@router.put('/studio/posts/{identifier}')
def update_post(request:Request,identifier:str,body:dict):
    with store(request).transaction() as db: return save(db,'posts',body,identifier)


@router.delete('/studio/posts/{identifier}')
def delete_post(request:Request,identifier:str,body:dict):
    with store(request).transaction() as db: remove(db,'posts',identifier,body.get('version'))
    return {'ok':True}


@router.post('/private/preview')
@router.post('/studio/preview')
def preview(body:dict): return markdown(text(body.get('content'),200000))


@router.get('/public/journal/{kind}')
@router.get('/studio/journal/{kind}')
def get_journal(request:Request,kind:str):
    choice(kind,['albums','moments'])
    with store(request).connect() as db:
        data=[journal_row(db,r) for r in db.execute('SELECT * FROM journal WHERE kind=? ORDER BY created DESC',(kind,))]
        return [r for r in data if r['status']=='published'] if '/public/' in request.url.path else data


@router.post('/studio/journal/{kind}',status_code=201)
def create_journal(request:Request,kind:str,body:dict):
    b=journal_data(kind,body); identifier=str(uuid4())
    with store(request).transaction() as db:
        check_images(db,b,'owner')
        db.execute('INSERT INTO journal(id,kind,userId,data,created,updated) VALUES(?,?,?,?,?,?)',(identifier,kind,'owner',dumps(b),stamp(),stamp()))
        return journal_row(db,db.execute('SELECT * FROM journal WHERE id=?',(identifier,)).fetchone())


@router.put('/studio/journal/{kind}/{identifier}')
@router.delete('/studio/journal/{kind}/{identifier}')
def update_journal(request:Request,kind:str,identifier:str,body:dict):
    choice(kind,['albums','moments'])
    with store(request).transaction() as db:
        row=db.execute('SELECT * FROM journal WHERE id=? AND kind=?',(identifier,kind)).fetchone()
        if not row: fail(404,'内容不存在')
        if body.get('version')!=row['version']: fail(409,'内容已更新，请刷新')
        if request.method=='DELETE':
            db.execute('DELETE FROM journal WHERE id=?',(identifier,)); return {'ok':True}
        b=journal_data(kind,body); check_images(db,b,'owner')
        db.execute('UPDATE journal SET data=?,version=version+1,updated=? WHERE id=?',(dumps(b),stamp(),identifier))
        return journal_row(db,db.execute('SELECT * FROM journal WHERE id=?',(identifier,)).fetchone())


@router.get('/studio/taxonomy')
def get_taxonomy(request:Request):
    with store(request).connect() as db: return taxonomy(db)


@router.post('/admin/taxonomy')
@router.put('/admin/taxonomy')
@router.delete('/admin/taxonomy')
def edit_taxonomy(request:Request,body:dict):
    kind=choice(body.get('kind'),['categories','tags']); name=taxonomy_name(body.get('name'))
    with store(request).transaction() as db:
        posts=list(db.execute("SELECT * FROM records WHERE kind='posts'"))
        if request.method=='POST': db.execute('INSERT OR IGNORE INTO taxonomy VALUES(?,?)',(kind,name))
        elif request.method=='DELETE':
            for row in posts:
                p=json.loads(row['data'])
                if (p['category']==name if kind=='categories' else name in p.get('tags','').split(',')): fail(409,'已有文章使用此项，请先调整文章或使用重命名')
            db.execute('DELETE FROM taxonomy WHERE kind=? AND name=?',(kind,name))
        else:
            old=taxonomy_name(body.get('old'))
            if not db.execute('SELECT name FROM taxonomy WHERE kind=? AND name=?',(kind,old)).fetchone(): fail(404,'分类或标签不存在')
            if old!=name and db.execute('SELECT name FROM taxonomy WHERE kind=? AND name=?',(kind,name)).fetchone(): fail(409,'此名称已存在')
            db.execute('UPDATE taxonomy SET name=? WHERE kind=? AND name=?',(name,kind,old))
            for row in posts:
                p=json.loads(row['data']); before=dumps(p)
                if kind=='categories' and p['category']==old: p['category']=name
                if kind=='tags': p['tags']=','.join(name if t.strip()==old else t.strip() for t in p.get('tags','').replace('，',',').split(','))
                if dumps(p)!=before: db.execute('UPDATE records SET data=?,version=version+1,updated=? WHERE id=?',(dumps(p),stamp(),row['id']))
        return taxonomy(db)


@router.get('/admin/site')
def admin_site(request:Request):
    with store(request).connect() as db: return site(db)


@router.put('/admin/site')
def edit_site(request:Request,body:dict):
    b=site_settings(body)
    with store(request).transaction() as db:
        check_images(db,b,'owner'); set_meta(db,'site',b); audit(db,'site:update')
    return b


@router.get('/admin/comments')
def admin_comments(request:Request,status:str='pending'):
    choice(status,['pending','approved','rejected'])
    with store(request).connect() as db:
        titles={p['id']:p['title'] for p in records(db,'posts')}
        return [{**dict(r),'postTitle':titles.get(r['postId'],'已删除文章')} for r in db.execute('SELECT * FROM comments WHERE status=? ORDER BY created DESC LIMIT 300',(status,))]


@router.put('/admin/comments/{identifier}')
def review_comment(request:Request,identifier:str,body:dict):
    status=choice(body.get('status'),['pending','approved','rejected'])
    with store(request).transaction() as db:
        old=db.execute('SELECT * FROM comments WHERE id=?',(identifier,)).fetchone()
        if not old: fail(404,'评论不存在')
        if body.get('version')!=old['version']: fail(409,'审核状态已变化，请刷新')
        db.execute('UPDATE comments SET status=?,version=version+1,updated=? WHERE id=?',(status,stamp(),identifier)); audit(db,'comment:'+status,identifier)
    return {'ok':True}


@router.get('/admin/registrations')
def registrations(request:Request,status:str='pending'):
    choice(status,['pending','approved','rejected'])
    with store(request).connect() as db: return [dict(r) for r in db.execute('SELECT id,username,name,reason,status,created,reviewed FROM registrations WHERE status=? ORDER BY created DESC LIMIT 300',(status,))]


@router.put('/admin/registrations/{identifier}')
def review_registration(request:Request,identifier:str,body:dict):
    status=choice(body.get('status'),['approved','rejected'])
    with store(request).transaction() as db:
        r=db.execute('SELECT * FROM registrations WHERE id=?',(identifier,)).fetchone()
        if not r: fail(404,'申请不存在')
        if r['status']!='pending': fail(409,'该申请已经处理')
        if status=='approved':
            if db.execute('SELECT id FROM users WHERE username=?',(r['username'],)).fetchone(): fail(409,'账号已存在')
            db.execute('INSERT INTO users(id,username,name,salt,hash,created) VALUES(?,?,?,?,?,?)',(str(uuid4()),r['username'],r['name'],r['salt'],r['hash'],stamp()))
        db.execute("UPDATE registrations SET status=?,reviewed=?,salt='',hash='' WHERE id=?",(status,stamp(),identifier))
    return {'ok':True}


@router.get('/admin/users')
def users(request:Request):
    with store(request).connect() as db: return [dict(r) for r in db.execute('SELECT id,username,name,disabled,created FROM users ORDER BY created')]


@router.post('/admin/users',status_code=201)
def create_user(request:Request,body:dict):
    username=text(body.get('username'),32,3); name=text(body.get('name'),80,1,True)
    if not re.fullmatch('[a-z0-9_-]{3,32}',username): fail(400,'账号格式无效')
    salt,hashed=credentials(body.get('password')); identifier=str(uuid4())
    with store(request).transaction() as db:
        if username=='admin' or db.execute('SELECT id FROM users WHERE username=?',(username,)).fetchone(): fail(409,'该账号已存在或保留')
        db.execute('INSERT INTO users(id,username,name,salt,hash,created) VALUES(?,?,?,?,?,?)',(identifier,username,name,salt,hashed,stamp())); audit(db,'reader:create',identifier)
    return {'id':identifier}


@router.put('/admin/users/{identifier}')
def update_user(request:Request,identifier:str,body:dict):
    hashed=credentials(body['password']) if 'password' in body else None
    if 'disabled' in body and not isinstance(body['disabled'],bool): fail(400,'停用选项无效')
    with store(request).transaction() as db:
        if not db.execute('SELECT id FROM users WHERE id=?',(identifier,)).fetchone(): fail(404,'读者不存在')
        if 'disabled' in body: db.execute('UPDATE users SET disabled=? WHERE id=?',(int(body['disabled']),identifier))
        if hashed: db.execute('UPDATE users SET salt=?,hash=? WHERE id=?',(*hashed,identifier))
        if 'disabled' in body or hashed: db.execute('DELETE FROM sessions WHERE userId=?',(identifier,))
        audit(db,'reader:update',identifier)
    return {'ok':True}


@router.get('/private/state')
def state(request:Request):
    with store(request).transaction() as db:
        settle_focus(db)
        return {'user':user(request),'accountProfile':profile(db,user(request)),'profile':meta(db,'profile',DEFAULT_PROFILE),'profileVersion':meta(db,'profileVersion',1),'story':meta(db,'story',DEFAULT_STORY),'focus':meta(db,'focus'),'sessions':records(db,'sessions','owner'),'progress':records(db,'progress','owner'),'awards':AWARDS,'records':{k:records(db,k,'owner') for k in CONTRACT['schemas']}}


@router.get('/private/documents')
def documents(request:Request):
    with store(request).connect() as db:
        return [dict(row) for row in db.execute('SELECT id,title,category,content,version,created,updated FROM private_documents ORDER BY updated DESC,id')]


@router.post('/private/documents',status_code=201)
def create_document(request:Request,body:dict):
    title=text(body.get('title'),180,1,True)
    category=text(body.get('category',''),80,0,True)
    content=text(body.get('content',''),200000)
    identifier=str(uuid4()); now=stamp()
    with store(request).transaction() as db:
        db.execute('INSERT INTO private_documents(id,title,category,content,version,created,updated) VALUES(?,?,?,?,1,?,?)',(identifier,title,category,content,now,now))
        audit(db,'document:create',identifier)
        return dict(db.execute('SELECT id,title,category,content,version,created,updated FROM private_documents WHERE id=?',(identifier,)).fetchone())


@router.put('/private/documents/{identifier}')
def update_document(request:Request,identifier:str,body:dict):
    title=text(body.get('title'),180,1,True)
    category=text(body.get('category',''),80,0,True)
    content=text(body.get('content',''),200000)
    version=number(body.get('version'),1,2**53,True)
    with store(request).transaction() as db:
        row=db.execute('SELECT version FROM private_documents WHERE id=?',(identifier,)).fetchone()
        if not row: fail(404,'文档不存在')
        if version!=row['version']: fail(409,'文档已在其他位置更新，请刷新后重试')
        db.execute('UPDATE private_documents SET title=?,category=?,content=?,version=version+1,updated=? WHERE id=?',(title,category,content,stamp(),identifier))
        audit(db,'document:update',identifier)
        return dict(db.execute('SELECT id,title,category,content,version,created,updated FROM private_documents WHERE id=?',(identifier,)).fetchone())


@router.delete('/private/documents/{identifier}')
def delete_document(request:Request,identifier:str,body:dict):
    version=number(body.get('version'),1,2**53,True)
    with store(request).transaction() as db:
        row=db.execute('SELECT version FROM private_documents WHERE id=?',(identifier,)).fetchone()
        if not row: fail(404,'文档不存在')
        if version!=row['version']: fail(409,'文档已在其他位置更新，请刷新后重试')
        db.execute('DELETE FROM private_documents WHERE id=?',(identifier,)); audit(db,'document:delete',identifier)
    return {'ok':True}


@router.post('/private/records/{kind}',status_code=201)
def create_record(request:Request,kind:str,body:dict):
    with store(request).transaction() as db: return save(db,kind,body)


@router.put('/private/records/{kind}/{identifier}')
def update_record(request:Request,kind:str,identifier:str,body:dict):
    with store(request).transaction() as db: return save(db,kind,body,identifier)


@router.delete('/private/records/{kind}/{identifier}')
def delete_record(request:Request,kind:str,identifier:str,body:dict):
    with store(request).transaction() as db: remove(db,kind,identifier,body.get('version'))
    return {'ok':True}


@router.put('/private/profile')
def life_profile(request:Request,body:dict):
    p=validate_schema(CONTRACT['profileSchema'],body)
    with store(request).transaction() as db:
        if body.get('version')!=meta(db,'profileVersion',1): fail(409,'资料已更新，请刷新后再保存',current=meta(db,'profile'),submitted=p)
        set_meta(db,'profile',p); set_meta(db,'profileVersion',meta(db,'profileVersion',1)+1)
    return p


@router.post('/private/password')
def password(request:Request,body:dict):
    with store(request).transaction() as db: rate(db,ip(request),'password',10)
    with store(request).transaction() as db:
        login(db,'admin',body.get('old')); salt,hashed=credentials(body.get('password'))
        set_meta(db,'account',{**meta(db,'account'),'salt':salt,'hash':hashed})
        db.execute("DELETE FROM sessions WHERE userId='owner'")
        response=JSONResponse({'ok':True}); session(db,response,'owner',request.app.state.secure); return response


@router.post('/private/story/{action}')
def story(request:Request,action:str):
    with store(request).transaction() as db: return story_action(db,action)


@router.post('/private/focus')
def focus(request:Request,body:dict):
    action=choice(body.get('action'),['start','pause','resume','cancel'])
    minutes=choice(body.get('minutes',25),[25,45,60]); task=text(body.get('task',''),200)
    with store(request).transaction() as db:
        settle_focus(db); f=meta(db,'focus')
        if action=='start':
            if f: fail(409,'已有专注在进行')
            f={'minutes':minutes,'remaining':minutes*60,'endAt':millis()+minutes*60000,'task':task}
        elif action=='pause' and f and f.get('endAt'): f.update(remaining=max(0,math.ceil((f['endAt']-millis())/1000)),endAt=None)
        elif action=='resume' and f and not f.get('endAt'): f['endAt']=millis()+f['remaining']*1000
        elif action=='cancel': f=None
        set_meta(db,'focus',f); return f


@router.get('/private/tokens')
def tokens(request:Request):
    with store(request).connect() as db: return [dict(r) for r in db.execute("SELECT id,name,expires,created FROM tokens WHERE userId='owner'")]


@router.post('/private/tokens')
def create_token(request:Request,body:dict):
    name=text(body.get('name'),100,1); token='space_'+secrets.token_hex(32); identifier=str(uuid4())
    with store(request).transaction() as db: db.execute('INSERT INTO tokens VALUES(?,?,?,?,?,?)',(identifier,sha(token),name,millis()+90*86400000,stamp(),'owner'))
    return {'id':identifier,'token':token}


@router.delete('/private/tokens/{identifier}')
def delete_token(request:Request,identifier:str):
    with store(request).transaction() as db: db.execute("DELETE FROM tokens WHERE id=? AND userId='owner'",(identifier,))
    return {'ok':True}


@router.post('/ingest')
def ingest(request:Request,body:dict):
    authorization=request.headers.get('authorization','')
    if not authorization.startswith('Bearer '): fail(401,'写入令牌无效或已过期')
    with store(request).transaction() as db:
        token=db.execute("SELECT * FROM tokens WHERE hash=? AND expires>? AND userId='owner'",(sha(authorization[7:]),millis())).fetchone()
        if not token: fail(401,'写入令牌无效或已过期')
        rate(db,token['id'],'ingest',300)
        kind=choice(body.get('kind'),['health','sleep','meals']); key=text(body.get('key'),200,1); source=text(body.get('source'),100,1)
        if not isinstance(body.get('data'),dict): fail(400,'数据格式无效')
        data=validate_record(kind,{**body['data'],'demo':False})
        digest=sha(dumps({'kind':kind,'source':source,'data':data}))
        old=db.execute('SELECT * FROM ingest WHERE token=? AND key=?',(token['id'],key)).fetchone()
        if old:
            # V8 hashes JS property order; validate against stored normalized record as well.
            existing=db.execute('SELECT data FROM records WHERE id=?',(old['recordId'],)).fetchone()
            previous=json.loads(existing['data']) if existing else {}
            if old['hash']!=digest and (not existing or previous.get('source')!=source or validate_record(kind,previous)!=data): fail(409,'同一幂等键对应不同内容')
            return {'id':old['recordId'],'replayed':True}
        unique(db,kind,data)
        r=insert(db,kind,{**data,'source':source,'receivedAt':stamp(),'idempotencyKey':key})
        db.execute('INSERT INTO ingest VALUES(?,?,?,?,?)',(token['id'],key,digest,r['id'],stamp())); unlock(db,'health')
        return {'id':r['id'],'replayed':False}


ACCESS_SCOPES={'content:draft:write','content:publish','content:import','automation:submit'}


@router.post('/v1/automation/results',status_code=201)
def submit_local_result(request:Request,body:dict):
    """Local heavy work pushes bounded text; never commands or credentials."""
    if not request.headers.get('authorization','').startswith('Bearer '):fail(401,'Access Token 无效或已过期')
    from .automation import flow_row, run_row
    identifier=text(body.get('flowId'),100,1);key=text(request.headers.get('idempotency-key',''),200,1)
    title=text(body.get('title'),180,1,True);content=text(body.get('content'),100000,1)
    with store(request).transaction() as db:
        token=require_access(db,request,'automation:submit')
        flow=db.execute("SELECT * FROM automation_flows WHERE id=? AND template='local-digest'",(identifier,)).fetchone()
        if not flow:fail(404,'本地资料任务不存在')
        request_key='local:'+token['id']+':'+key
        existing=db.execute('SELECT * FROM automation_runs WHERE requestKey=?',(request_key,)).fetchone()
        result={'title':title,'text':content,'items':[],'warnings':[]};digest=sha(dumps(result))
        if existing:
            if json.loads(existing['result']).get('submissionHash')!=digest:fail(409,'幂等键已用于不同结果')
            return run_row(existing)
        if meta(db,'automationPaused',False):fail(409,'自动化已暂停')
        result['submissionHash']=digest;run_id=str(uuid4());now=stamp()
        db.execute('INSERT INTO automation_runs(id,flowId,snapshot,state,requestKey,result,created,updated) VALUES(?,?,?,?,?,?,?,?)',(run_id,identifier,dumps(flow_row(flow)),'waiting_approval',request_key,dumps(result),now,now));audit(db,'automation:local-submit',run_id)
        return run_row(db.execute('SELECT * FROM automation_runs WHERE id=?',(run_id,)).fetchone())


def _mail_config(db):
    from .mailing import CONFIG_KEY, meta
    return meta(db, CONFIG_KEY, {})


def deliver_report(app, kind, scheduled_key=None, data=None):
    from .mailing import DeliveryUnknown, report, report_text, send_email
    from .storage import meta
    with app.state.store.connect() as db:
        config = meta(db, 'mailSettings', {})
        data = data or report(db)
    if not config.get('enabled') and kind == 'scheduled': return {'status':'paused'}
    identifier=str(uuid4()); subject='个人空间周报'
    try:
        with app.state.store.transaction() as db:
            db.execute('INSERT INTO email_runs(id,kind,status,subject,recipient,scheduledKey,created) VALUES(?,?,?,?,?,?,?)',(identifier,kind,'sending',subject,config.get('recipient',''),scheduled_key,stamp()))
            if scheduled_key:
                current=meta(db,'mailSettings',{}); current['lastScheduledKey']=scheduled_key; set_meta(db,'mailSettings',current)
    except sqlite3.IntegrityError:
        return {'status':'duplicate'}
    try:
        send_email(config,subject,report_text(data,os.getenv('SITE_URL','http://localhost')))
        state='succeeded'; error=''
    except DeliveryUnknown:
        state='unknown'; error='邮件服务器未确认投递结果，请检查收件箱后再处理'
    except Exception as exc:
        state='failed'; error=type(exc).__name__
        logging.getLogger('lin-notebook.mail').warning('Email delivery failed: %s', type(exc).__name__)
    with app.state.store.transaction() as db:
        db.execute('UPDATE email_runs SET status=?,finished=?,error=? WHERE id=?',(state,stamp(),error,identifier))
        if kind in ('manual','retry'): audit(db,'mail:'+kind,identifier)
    return {'id':identifier,'status':state,'error':error or None}


def require_owner(request):
    current=user(request)
    if not current or current.get('role')!='admin': fail(401,'请先以站主身份登录')


def require_access(db,request,scope):
    authorization=request.headers.get('authorization','')
    if not authorization.startswith('Bearer '): fail(401,'Access Token 无效或已过期')
    raw=authorization[7:]
    token=db.execute('SELECT * FROM access_tokens WHERE hash=? AND expires>? AND userId=\'owner\'',(sha(raw),millis())).fetchone()
    if not token: fail(401,'Access Token 无效或已过期')
    scopes=set(json.loads(token['scopes']))
    if scope not in scopes: fail(403,'Access Token 缺少所需权限')
    db.execute('UPDATE access_tokens SET lastUsed=? WHERE id=?',(millis(),token['id']))
    rate(db,token['id'],'access:'+scope,300)
    return token


@router.get('/private/access-tokens')
def list_access_tokens(request:Request):
    require_owner(request)
    with store(request).connect() as db:
        return [dict(r) | {'scopes':json.loads(r['scopes'])} for r in db.execute("SELECT id,prefix,name,scopes,expires,created,lastUsed FROM access_tokens WHERE userId='owner' ORDER BY created DESC")]


@router.post('/private/access-tokens')
def create_access_token(request:Request,body:dict):
    require_owner(request)
    name=text(body.get('name'),100,1,True)
    scopes=body.get('scopes',['content:draft:write'])
    if not isinstance(scopes,list) or not scopes or any(not isinstance(s,str) or s not in ACCESS_SCOPES for s in scopes): fail(400,'Access Token 权限范围无效')
    scopes=sorted(set(scopes))
    days=number(body.get('expiresInDays',90),1,365,True)
    raw='sk-'+secrets.token_urlsafe(40); identifier=str(uuid4()); prefix=raw[:11]
    expires=millis()+days*86400000
    with store(request).transaction() as db:
        db.execute('INSERT INTO access_tokens(id,hash,prefix,name,scopes,expires,created,userId) VALUES(?,?,?,?,?,?,?,\'owner\')',(identifier,sha(raw),prefix,name,dumps(scopes),expires,stamp()))
        audit(db,'access-token:create',identifier)
    return {'id':identifier,'token':raw,'prefix':prefix,'name':name,'scopes':scopes,'expires':expires}


@router.delete('/private/access-tokens/{identifier}')
def revoke_access_token(request:Request,identifier:str):
    require_owner(request)
    with store(request).transaction() as db:
        db.execute("DELETE FROM access_tokens WHERE id=? AND userId='owner'",(identifier,))
        db.execute('DELETE FROM api_idempotency WHERE tokenId=?',(identifier,))
        audit(db,'access-token:revoke',identifier)
    return {'ok':True}


@router.post('/v1/posts',status_code=201)
def access_create_post(request:Request,body:dict):
    requested=choice(body.get('requestedState','draft'),['draft','published'])
    scope='content:publish' if requested=='published' else 'content:draft:write'
    key=text(request.headers.get('idempotency-key',''),200,1)
    data={
        'title':body.get('title'), 'slug':body.get('slug'), 'excerpt':body.get('excerpt',''),
        'content':body.get('content'), 'category':body.get('category','日常手记'),
        'tags':body.get('tags',''), 'cover':body.get('cover',''), 'status':requested,
        'publishAt':body.get('publishAt') or stamp(), 'featured':False, 'type':1,
        'origin_url':'', 'order':None, 'demo':False
    }
    with store(request).transaction() as db:
        token=require_access(db,request,scope)
        digest_data={**data,'publishAt':body.get('publishAt')}
        digest=sha(dumps(digest_data))
        old=db.execute('SELECT hash,recordId FROM api_idempotency WHERE tokenId=? AND key=?',(token['id'],key)).fetchone()
        if old:
            if old['hash']!=digest: fail(409,'同一 Idempotency-Key 已用于不同内容')
            existing=db.execute('SELECT * FROM records WHERE id=? AND kind=\'posts\'',(old['recordId'],)).fetchone()
            if existing: return {'id':old['recordId'],'version':existing['version'],'replayed':True}
            fail(409,'幂等记录已失效，请使用新的 Idempotency-Key')
        saved=save(db,'posts',data)
        db.execute('INSERT INTO api_idempotency VALUES(?,?,?,?,?)',(token['id'],key,digest,saved['id'],stamp()))
        return {'id':saved['id'],'version':saved['version'],'status':saved['status'],'replayed':False}


@router.post('/v1/imports/validate')
@router.post('/private/imports/validate')
def validate_content_import(request:Request,body:dict):
    if not isinstance(body.get('posts'),list) or len(body['posts'])>50: fail(400,'一次最多校验 50 篇文章')
    with store(request).connect() as db:
        if request.url.path.startswith('/api/private/'):require_owner(request)
        else:require_access(db,request,'content:import')
        errors=[]; normalized=[]; seen=set()
        for index,item in enumerate(body['posts']):
            try:
                if not isinstance(item,dict): fail(400,'文章必须是对象')
                if item.get('requestedState','draft')!='draft': fail(400,'导入仅能创建草稿')
                data=validate_record('posts',{
                    'title':item.get('title'),'slug':item.get('slug'),'excerpt':item.get('excerpt',''),
                    'content':item.get('content'),'category':item.get('category','日常手记'),
                    'tags':item.get('tags',''),'cover':item.get('cover',''),'status':'draft',
                    'publishAt':item.get('publishAt') or stamp(),'demo':False
                })
                check_images(db,data,'owner')
                if data['slug'] in seen or db.execute("SELECT 1 FROM records WHERE kind='posts' AND deleted IS NULL AND json_extract(data,'$.slug')=?",(data['slug'],)).fetchone(): fail(409,'文章链接已存在')
                seen.add(data['slug']); normalized.append(data)
            except Problem as error:
                errors.append({'index':index,'message':error.message})
        return {'valid':not errors,'count':len(normalized),'errors':errors}


@router.post('/v1/imports',status_code=201)
@router.post('/private/imports',status_code=201)
def import_content(request:Request,body:dict):
    rows=body.get('posts')
    if not isinstance(rows,list) or not 1<=len(rows)<=50: fail(400,'一次导入 1–50 篇文章')
    with store(request).transaction() as db:
        if request.url.path.startswith('/api/private/'):require_owner(request)
        else:require_access(db,request,'content:import')
        normalized=[]; seen=set()
        for item in rows:
            if not isinstance(item,dict) or item.get('requestedState','draft')!='draft': fail(400,'导入仅能创建草稿')
            data=validate_record('posts',{'title':item.get('title'),'slug':item.get('slug'),'excerpt':item.get('excerpt',''),'content':item.get('content'),'category':item.get('category','日常手记'),'tags':item.get('tags',''),'cover':item.get('cover',''),'status':'draft','publishAt':item.get('publishAt') or stamp(),'demo':False})
            check_images(db,data,'owner')
            if data['slug'] in seen or db.execute("SELECT 1 FROM records WHERE kind='posts' AND deleted IS NULL AND json_extract(data,'$.slug')=?",(data['slug'],)).fetchone(): fail(409,'文章链接已存在')
            seen.add(data['slug']); normalized.append(data)
        created=[save(db,'posts',row) for row in normalized]
        audit(db,'content:import',','.join(row['id'] for row in created))
        return {'created':[{'id':row['id'],'slug':row['slug']} for row in created]}


@router.get('/private/mail/settings')
def mail_settings(request:Request):
    require_owner(request)
    from .mailing import settings
    with store(request).connect() as db: return settings(db)


@router.put('/private/mail/settings')
def put_mail_settings(request:Request,body:dict):
    require_owner(request)
    from .mailing import save_settings
    try:
        with store(request).transaction() as db: result=save_settings(db,body)
    except (ValueError,RuntimeError) as error: fail(400,str(error))
    return result


@router.post('/private/mail/test')
def mail_test(request:Request,body:dict):
    require_owner(request)
    from .mailing import connection_error, send_email
    with store(request).transaction() as db:
        rate(db,ip(request),'mail-test',5,600)
        config=_mail_config(db)
    try:
        from .mailing import valid_email
        target=body.get('recipient') or config.get('recipient')
        if not valid_email(target): fail(400,'测试收件邮箱无效')
        send_email(config,'个人空间邮件配置测试','SMTP 连接和邮件发送正常。',target)
    except (ValueError,RuntimeError) as error: fail(400,str(error))
    except Exception as error:
        logging.getLogger('lin-notebook.mail').warning('SMTP test failed: %s',type(error).__name__)
        fail(502,connection_error(error))
    return {'ok':True,'recipient':target}


@router.get('/private/mail/preview')
def mail_preview(request:Request):
    require_owner(request)
    from .mailing import report, report_text
    with store(request).connect() as db:
        data=report(db)
        return {**data,'subject':'个人空间周报','text':report_text(data,request.app.state.site_url)}


@router.post('/private/mail/send')
def mail_send(request:Request):
    require_owner(request)
    from .mailing import report
    with store(request).transaction() as db:
        rate(db,ip(request),'mail-send',10,600)
        data=report(db)
    return deliver_report(request.app,'manual',data=data)


@router.get('/private/mail/runs')
def mail_runs(request:Request):
    require_owner(request)
    with store(request).connect() as db:
        return [dict(row) for row in db.execute('SELECT id,kind,status,subject,recipient,created,finished,error FROM email_runs ORDER BY created DESC LIMIT 30')]


@router.post('/private/mail/runs/{identifier}/retry')
def retry_mail(request:Request,identifier:str):
    require_owner(request)
    from .mailing import report
    with store(request).transaction() as db:
        rate(db,ip(request),'mail-retry',5,600)
        old=db.execute("SELECT status FROM email_runs WHERE id=?",(identifier,)).fetchone()
        if not old: fail(404,'投递记录不存在')
        if old['status']!='failed': fail(409,'只有明确失败的邮件可以重试')
        data=report(db)
    return deliver_report(request.app,'retry',data=data)


@router.delete('/private/demo')
def archive_demo(request:Request):
    with store(request).transaction() as db:
        db.execute("UPDATE records SET deleted=?,version=version+1 WHERE deleted IS NULL AND userId='owner' AND json_extract(data,'$.demo')=1",(stamp(),)); audit(db,'archive-demo')
    return {'ok':True}


@router.get('/private/audit')
def get_audit(request:Request):
    with store(request).connect() as db: return [dict(r) for r in db.execute("SELECT id,event,recordId,created FROM audit WHERE userId='owner' ORDER BY id DESC LIMIT 100")]
