"""Read models for replaceable frontends. Public projections never expose workspace data."""
import json
import os
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Request

from .content import author, image_visible, journal_row, site
from .page_layout import config as layout_config
from .reference_docs import DEFAULTS, EMBED_ORIGINS
from .storage import meta, record
from .validation import CONTRACT, DEFAULT_PROFILE, choice, fail

router = APIRouter(prefix='/api', tags=['Frontend read models'])


@router.get('/public/status')
def public_status(request: Request):
    with request.app.state.store.connect() as db:
        db.execute('SELECT 1').fetchone()
        started = site(db).get('siteStartedAt', '')
    return {'ok': True, 'version': '10.0.0', 'siteStartedAt': started,
            'checkedAt': datetime.now(timezone.utc).isoformat()}


def page_result(items, total, page, page_size):
    return {'items': items, 'total': total, 'page': page, 'pageSize': page_size, 'hasMore': page * page_size < total}


def current_season():
    now = datetime.now(ZoneInfo('Asia/Shanghai'))
    return f'{now.year}-Q{(now.month-1)//3+1}'


def post_page(db, q='', category='', tag='', page=1, page_size=12):
    where=["kind='posts'",'deleted IS NULL',"json_extract(data,'$.status') IN ('published','scheduled')","julianday(json_extract(data,'$.publishAt'))<=julianday('now')"]
    args=[]
    if q:
        where.append("(instr(lower(json_extract(data,'$.title')),lower(?))>0 OR instr(lower(coalesce(json_extract(data,'$.excerpt'),'')),lower(?))>0)")
        args.extend([q,q])
    if category:where.append("json_extract(data,'$.category')=?");args.append(category)
    if tag:
        where.append("instr(','||replace(replace(coalesce(json_extract(data,'$.tags'),''),'，',','),' ','')||',',','||?||',')>0")
        args.append(tag)
    condition=' AND '.join(where)
    total=db.execute('SELECT count(*) FROM records WHERE '+condition,args).fetchone()[0]
    fields=('title','slug','cover','excerpt','publishAt','category','tags','featured','status','order','type')
    projection=','.join("json_extract(data,'$."+k+"') AS '"+k+"'" for k in fields)
    rows=db.execute('SELECT id,userId,updated,'+projection+' FROM records WHERE '+condition+" ORDER BY coalesce(json_extract(data,'$.featured'),0) DESC,coalesce(json_extract(data,'$.order'),999),julianday(json_extract(data,'$.publishAt')) DESC,id LIMIT ? OFFSET ?",[*args,page_size,(page-1)*page_size])
    authors={};items=[]
    for row in rows:
        item=dict(row);uid=item.pop('userId')
        if uid not in authors:authors[uid]=author(db,uid)
        items.append({**item,**authors[uid]})
    return page_result(items,total,page,page_size)


@router.get('/public/catalog/posts')
def posts(request:Request,q:str=Query('',max_length=100),category:str=Query('',max_length=80),tag:str=Query('',max_length=80),page:int=Query(1,ge=1,le=100000),pageSize:int=Query(12,ge=1,le=100)):
    with request.app.state.store.connect() as db:return post_page(db,q,category,tag,page,pageSize)


def public_bookmarks(db):
    from urllib.parse import urlsplit
    rows = meta(db, 'referenceDocs', {'items': DEFAULTS})['items']
    return [{**row, 'embeddable': f'{urlsplit(row["url"]).scheme}://{urlsplit(row["url"]).netloc}' in EMBED_ORIGINS}
            for row in rows if row.get('public') is True]


def anime_page(db, season='', q='', weekday='', page=1, page_size=24):
    if season and not re.fullmatch(r'[0-9]{4}-Q[1-4]', season): fail(400, '季度格式无效')
    if weekday: choice(weekday, ['一', '二', '三', '四', '五', '六', '日', 'unknown'])
    where = ["r.kind='library'", "r.userId='owner'", 'r.deleted IS NULL', "json_extract(r.data,'$.kind')='番剧'"]
    args = []
    visible = "json_extract(r.data,'$.public')=1"
    if meta(db, 'pageLayout', {}).get('animeAutoPublic', True):
        visible += ' OR EXISTS(SELECT 1 FROM automation_items a WHERE a.recordId=r.id)'
    where.append('(' + visible + ')')
    base = ' AND '.join(where)
    seasons = [row[0] for row in db.execute("SELECT DISTINCT json_extract(r.data,'$.season') FROM records r WHERE " + base + " AND coalesce(json_extract(r.data,'$.season'),'')<>'' ORDER BY 1 DESC")]
    if season: where.append("json_extract(r.data,'$.season')=?"); args.append(season)
    if q: where.append("(instr(lower(json_extract(r.data,'$.title')),lower(?))>0 OR instr(lower(coalesce(json_extract(r.data,'$.tags'),'')),lower(?))>0)"); args.extend([q, q])
    # Project metadata in SQLite: private notes never enter this read model.
    fields=('title','cover','season','broadcast','creator','tags')
    projection=','.join("coalesce(json_extract(r.data,'$."+key+"'),'') AS '"+key+"'" for key in fields)
    condition=' AND '.join(where)
    total=db.execute('SELECT count(*) FROM records r WHERE '+condition,args).fetchone()[0]
    query='SELECT r.id,'+projection+' FROM records r WHERE '+condition+' ORDER BY r.created DESC,r.id'
    if not weekday:query+=' LIMIT ? OFFSET ?';args.extend([page_size,(page-1)*page_size])
    rows = db.execute(query,args)
    items = []
    for row in rows:
        data = dict(row)
        match = re.search(r'(?:周|星期|礼拜)([一二三四五六日天])', data.get('broadcast', ''))
        day = ('日' if match[1]=='天' else match[1]) if match else ''
        if weekday and (day != weekday if weekday != 'unknown' else bool(day)): continue
        items.append({'id': row['id'], **{key: data.get(key, '') for key in ('title', 'cover', 'season', 'broadcast', 'creator', 'tags')}, 'weekday': day})
    if weekday:total=len(items);items=items[(page-1)*page_size:page*page_size]
    return {**page_result(items,total,page,page_size), 'seasons': seasons}


@router.get('/public/catalog/anime')
def anime(request: Request, season: str='', q: str=Query('', max_length=100), weekday: str='', page: int=Query(1, ge=1, le=100000), pageSize: int=Query(24, ge=1, le=100)):
    with request.app.state.store.connect() as db:
        return anime_page(db, season, q, weekday, page, pageSize)


@router.get('/public/bootstrap')
def bootstrap(request: Request):
    """Small initial payload; excludes post bodies and all private configuration."""
    with request.app.state.store.connect() as db:
        layout = layout_config(db)
        public_layout = {key: value for key, value in layout.items() if key != 'room'}
        s = site(db)
        posts=post_page(db,page_size=12)['items']
        photos = layout['introPhotos'] if layout['introPhotoMode']=='custom' else list(dict.fromkeys([v if v.startswith('/') else '/assets/'+v+'.webp' for v in s['heroImages']]+[p['cover'] for p in posts if p['cover']]))[:18]
        return {'apiVersion': '1', 'site': s, 'layout': public_layout,
                'featuredPosts':posts[:12],
                'intro': {'enabled': layout['introEnabled'] and s['motion'], 'title': layout['introTitle'] or s['title'], 'photos': photos, 'replay': layout['introReplay']},
                'navigation': [{'id': key, 'label': label, 'path': path} for key, label, path in [('home','首页','/'),('articles','文章','/blog'),('anime','番剧','/anime'),('moments','说说','/moments'),('albums','相册','/albums'),('about','关于','/about')]]}


@router.get('/public/home')
def home(request: Request):
    with request.app.state.store.connect() as db:
        layout = layout_config(db)
        modules = []
        for module in layout['home']:
            if not module['enabled']: continue
            key = module['id']; data = {}
            if key=='anime':
                season = current_season() if layout['animeSeason']=='auto' else layout['animeSeason']
                data = {**anime_page(db, season=season, page_size=layout['animeLimit']), 'season': season}
            elif key=='web':
                rows = public_bookmarks(db)
                data = {'items': rows, 'selected': next((r for r in rows if r['id']==layout['webDocumentId']), rows[0] if rows else None)}
            elif key=='profile':
                p = meta(db, 'profile', DEFAULT_PROFILE)
                data = {k: p.get(k, '') for k in ('name','tagline','bio')}
            elif key=='articles':
                data=post_page(db,page_size=5)
            elif key in ('moments','albums'):
                rows = db.execute("SELECT * FROM journal WHERE kind=? AND json_extract(data,'$.status')='published' ORDER BY created DESC,id LIMIT 3", (key,))
                data = {'items': [journal_row(db, row) for row in rows]}
            modules.append({'id': key, 'data': data})
        return {'accent': layout['accent'], 'modules': modules}


@router.get('/private/overview')
def overview(request: Request):
    with request.app.state.store.connect() as db:
        def count(sql): return db.execute(sql).fetchone()[0]
        mail=meta(db,'mailSettings',{})
        return {'content': {'posts': count("SELECT count(*) FROM records WHERE kind='posts' AND deleted IS NULL"), 'drafts': count("SELECT count(*) FROM records WHERE kind='posts' AND deleted IS NULL AND json_extract(data,'$.status')='draft'"), 'documents': count('SELECT count(*) FROM private_documents')},
                'review': {'comments': count("SELECT count(*) FROM comments WHERE status='pending'"), 'registrations': count("SELECT count(*) FROM registrations WHERE status='pending'")},
                'automation': {'paused': meta(db,'automationPaused',False), 'flows': count('SELECT count(*) FROM automation_flows'), 'active': count("SELECT count(*) FROM automation_runs WHERE state IN ('queued','running')"), 'waiting': count("SELECT count(*) FROM automation_runs WHERE state='waiting_approval'"), 'failed': count("SELECT count(*) FROM automation_runs WHERE state IN ('failed','delivery_failed','delivery_unknown')")},
                'mail': {'configured': all(bool(mail.get(key)) for key in ('host','sender','recipient','username','password')), 'encryptionReady': bool(os.getenv('EMAIL_ENCRYPTION_KEY'))},
                'recent': [dict(row) for row in db.execute('SELECT event,recordId,created FROM audit ORDER BY id DESC LIMIT 8')]}


@router.get('/private/catalog/records/{kind}')
def record_list(request: Request, kind: str, q: str=Query('', max_length=100), subtype: str=Query('',max_length=80), season: str=Query('all',max_length=7), page: int=Query(1, ge=1, le=100000), pageSize: int=Query(24, ge=1, le=100)):
    if kind not in CONTRACT['schemas']: fail(404,'记录类型不存在')
    where = ['kind=?', "userId='owner'", 'deleted IS NULL']; args = [kind]
    if q: where.append("instr(lower(coalesce(json_extract(data,'$.title'),'')),lower(?))>0"); args.append(q)
    if subtype: where.append("json_extract(data,'$.kind')=?"); args.append(subtype)
    with request.app.state.store.connect() as db:
        seasons=[r[0] for r in db.execute("SELECT DISTINCT json_extract(data,'$.season') FROM records WHERE "+' AND '.join(where)+" AND coalesce(json_extract(data,'$.season'),'')<>'' ORDER BY 1 DESC",args)]
        if season!='all':
            if season and not re.fullmatch(r'[0-9]{4}-Q[1-4]',season):fail(400,'季度格式无效')
            where.append("coalesce(json_extract(data,'$.season'),'')=?");args.append(season)
        condition = ' AND '.join(where)
        total = db.execute('SELECT count(*) FROM records WHERE '+condition, args).fetchone()[0]
        rows = [record(r) for r in db.execute('SELECT * FROM records WHERE '+condition+' ORDER BY updated DESC,id LIMIT ? OFFSET ?', [*args,pageSize,(page-1)*pageSize])]
        if kind=='library':
            imported = {r[0] for r in db.execute('SELECT recordId FROM automation_items')}
            auto = meta(db,'pageLayout',{}).get('animeAutoPublic',True)
            for row in rows: row['imported'] = row['id'] in imported; row['effectivePublic'] = row.get('kind')=='番剧' and (row.get('public') is True or (auto and row['imported']))
        return {**page_result(rows,total,page,pageSize),'seasons':seasons}


@router.get('/private/catalog/documents')
def document_list(request: Request, q: str=Query('', max_length=100), category: str=Query('',max_length=80), page: int=Query(1,ge=1,le=100000), pageSize: int=Query(24,ge=1,le=100)):
    where=['1=1']; args=[]
    if q: where.append('(instr(lower(title),lower(?))>0 OR instr(lower(content),lower(?))>0)'); args.extend([q,q])
    if category: where.append('category=?'); args.append(category)
    with request.app.state.store.connect() as db:
        condition=' AND '.join(where)
        total=db.execute('SELECT count(*) FROM private_documents WHERE '+condition,args).fetchone()[0]
        rows=[dict(r) for r in db.execute('SELECT id,title,category,version,created,updated,substr(content,1,160) AS excerpt FROM private_documents WHERE '+condition+' ORDER BY updated DESC,id LIMIT ? OFFSET ?',[*args,pageSize,(page-1)*pageSize])]
        return {**page_result(rows,total,page,pageSize),'categories':[r[0] for r in db.execute("SELECT DISTINCT category FROM private_documents WHERE category<>'' ORDER BY category")]}


@router.get('/private/documents/{identifier}')
def document_detail(request: Request, identifier: str):
    with request.app.state.store.connect() as db:
        row=db.execute('SELECT * FROM private_documents WHERE id=?',(identifier,)).fetchone()
        if not row: fail(404,'文档不存在')
        return dict(row)


@router.get('/private/media')
def media(request: Request, q: str=Query('',max_length=100), source: str='all', page: int=Query(1,ge=1,le=100000), pageSize: int=Query(24,ge=1,le=100)):
    choice(source,['all','uploads','assets'])
    from .main import ROOT
    rows=[]
    with request.app.state.store.connect() as db:
        if source in ('all','uploads'):
            for row in db.execute("SELECT name FROM upload_owners WHERE userId='owner' ORDER BY name"):
                if not re.fullmatch(r'[A-Za-z0-9_-]+\.(?:png|jpg|jpeg|webp)',row['name']):continue
                dest=request.app.state.store.directory/'uploads'/row['name']
                if dest.is_file() and q.casefold() in row['name'].casefold(): rows.append({'url':'/uploads/'+row['name'],'name':row['name'],'source':'uploads','bytes':dest.stat().st_size})
        if source in ('all','assets'):
            for dest in (ROOT/'public/assets').glob('*'):
                if dest.suffix.lower() in ('.png','.jpg','.jpeg','.webp') and dest.is_file() and q.casefold() in dest.name.casefold():rows.append({'url':'/assets/'+dest.name,'name':dest.name,'source':'assets','bytes':dest.stat().st_size})
        rows.sort(key=lambda item:(item['source'],item['name']))
        total=len(rows); rows=rows[(page-1)*pageSize:page*pageSize]
        for row in rows:row['public']=row['source']=='assets' or image_visible(db,row['url'])
        return page_result(rows,total,page,pageSize)


@router.get('/private/api-contract')
def api_contract(request: Request):
    """Authenticated even in production; never contains runtime secrets."""
    return {'apiVersion':'1','openapi':request.app.openapi(),'recordSchemas':CONTRACT['schemas'],
            'conventions':{'pagination':['items','total','page','pageSize','hasMore'],'concurrency':'PUT/DELETE carry version; refresh after 409','auth':'same-origin session cookie; /api/v1 uses scoped Bearer tokens','images':'Use server URLs; never construct upload paths or put API credentials in a frontend bundle'}}
