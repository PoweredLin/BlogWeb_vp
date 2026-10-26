"""Legacy personal export/import. Full site backups are provided by the CLI."""
import base64
import json
import re
import sqlite3
from uuid import UUID
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from .storage import meta,set_meta,dumps,stamp,audit
from .validation import CONTRACT,DEFAULT_PROFILE,DEFAULT_STORY,validate_schema,validate_record,fail,number,choice,text
from .security import check_images,validate_image,millis
from .content import day,add_taxonomy

router=APIRouter(prefix='/api/private')


@router.get('/backup')
def export(request:Request):
    store=request.app.state.store
    with store.connect() as db:
        uploads={}
        for path in (store.directory/'uploads').iterdir():
            owner=db.execute('SELECT userId FROM upload_owners WHERE name=?',(path.name,)).fetchone()
            if path.is_file() and (not owner or owner['userId']=='owner'): uploads[path.name]=base64.b64encode(path.read_bytes()).decode()
        data={'format':'daily-space-v1','exported':stamp(),'profile':meta(db,'profile',DEFAULT_PROFILE),'story':meta(db,'story',DEFAULT_STORY),'records':[dict(r) for r in db.execute("SELECT * FROM records WHERE userId='owner'")],'uploads':uploads}
    return JSONResponse(data,headers={'Content-Disposition':f'attachment; filename="daily-space-{day()}.json"'})


@router.post('/restore')
def restore(request:Request,body:dict):
    if body.get('format')!='daily-space-v1': fail(400,'备份格式无效')
    p=validate_schema(CONTRACT['profileSchema'],body.get('profile'))
    story=body.get('story'); rows=body.get('records'); uploads=body.get('uploads')
    if not isinstance(story,dict) or not isinstance(rows,list) or len(rows)>100000 or not isinstance(uploads,dict): fail(400,'备份内容无效')
    choice(story.get('round'),[1,2]); number(story.get('points'),-100,200); choice(story.get('phase'),['normal','transition','epilogue'])
    number(story.get('lastClick'),0,2**53); number(story.get('scene'),0,2**53,True); text(story.get('lastLine'),1000)
    if not isinstance(story.get('unlocks'),dict) or not isinstance(story.get('seen'),list) or len(story['seen'])>100: fail(400,'故事存档无效')
    for value in story['unlocks'].values(): number(value,0,2**53)
    for value in story['seen']: text(value,1000)
    store=request.app.state.store; ids=set(); decoded={}
    with store.connect() as db:
        for r in rows:
            if not isinstance(r,dict): fail(400,'备份记录无效')
            try: UUID(r.get('id','')); data=json.loads(r.get('data',''))
            except (ValueError,TypeError): fail(400,'备份记录无效')
            if r['id'] in ids: fail(400,'备份包含重复 ID')
            ids.add(r['id']); number(r.get('version'),1,2**53,True)
            for k in ('created','updated'): text(r.get(k),100,1)
            if r.get('deleted') is not None: text(r['deleted'],100,1)
            other=db.execute('SELECT userId FROM records WHERE id=?',(r['id'],)).fetchone()
            if other and other['userId']!='owner': fail(409,'备份包含不属于本站主的记录')
            if r['kind'] in ('progress','sessions'):
                text(data.get('date'),10,10)
                if r['kind']=='progress': text(data.get('title'),200); number(data.get('delta'),-1000000,1000000); text(data.get('libraryId'),100)
                else: number(data.get('minutes'),1,1440); text(data.get('task'),200)
            else: validate_record(r['kind'],data)
            check_images(db,data,'owner')
        slugs=set(); dates=set()
        for r in rows:
            if r.get('deleted'): continue
            data=json.loads(r['data'])
            if r['kind']=='posts':
                if data['slug'] in slugs: fail(400,'备份包含重复文章链接')
                slugs.add(data['slug'])
            if r['kind'] in ('health','sleep','notes'):
                key=(r['kind'],data['date'])
                if key in dates: fail(400,'备份包含重复日期记录')
                dates.add(key)
        for name,value in uploads.items():
            if not re.fullmatch(r'[\w-]+\.(png|jpeg|webp)',name,re.ASCII): fail(400,'备份图片名称无效')
            try: raw=base64.b64decode(value,validate=True)
            except (ValueError,TypeError): fail(400,'备份图片无效')
            validate_image(raw,name.rsplit('.',1)[1]); decoded[name]=raw
            owner=db.execute('SELECT userId FROM upload_owners WHERE name=?',(name,)).fetchone()
            if owner and owner['userId']!='owner': fail(403,'备份图片不属于本站主')
            dest=store.directory/'uploads'/name
            if dest.exists() and dest.read_bytes()!=raw: fail(409,'备份图片与当前同名文件不一致')
        safety=store.directory/'restore-safety'; safety.mkdir(exist_ok=True)
        with sqlite3.connect(safety/f'before-{millis()}.sqlite') as target: db.backup(target)
    created=[]
    try:
        with store.transaction() as db:
            for name,raw in decoded.items():
                dest=store.directory/'uploads'/name
                if not dest.exists(): dest.write_bytes(raw); created.append(dest)
                db.execute("INSERT OR IGNORE INTO upload_owners VALUES(?,'owner')",(name,))
            db.execute("DELETE FROM records WHERE userId='owner'")
            db.execute("DELETE FROM ingest WHERE token IN (SELECT id FROM tokens WHERE userId='owner')")
            for r in rows:
                db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?,?)',(r['id'],r['kind'],r['data'],r['version'],r['created'],r['updated'],r.get('deleted'),'owner'))
                if r['kind']=='posts':
                    add_taxonomy(db,json.loads(r['data'])); db.execute("INSERT INTO post_owners VALUES(?,'owner') ON CONFLICT(postId) DO UPDATE SET userId='owner'",(r['id'],))
            set_meta(db,'profile',p); set_meta(db,'profileVersion',meta(db,'profileVersion',1)+1); set_meta(db,'story',story); set_meta(db,'focus',None); audit(db,'restore')
    except BaseException:
        for path in created: path.unlink(missing_ok=True)
        raise
    return {'ok':True}
