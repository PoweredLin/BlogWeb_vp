"""Stable V8 API paths, backed entirely by Python/SQLite."""
import base64
import copy
import json
import math
import re
import secrets
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


@router.delete('/private/demo')
def archive_demo(request:Request):
    with store(request).transaction() as db:
        db.execute("UPDATE records SET deleted=?,version=version+1 WHERE deleted IS NULL AND userId='owner' AND json_extract(data,'$.demo')=1",(stamp(),)); audit(db,'archive-demo')
    return {'ok':True}


@router.get('/private/audit')
def get_audit(request:Request):
    with store(request).connect() as db: return [dict(r) for r in db.execute("SELECT id,event,recordId,created FROM audit WHERE userId='owner' ORDER BY id DESC LIMIT 100")]
