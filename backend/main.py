import logging
import os
import re
import sqlite3
import asyncio
from contextlib import asynccontextmanager
from email.utils import formatdate
from html import escape
from pathlib import Path
from urllib.parse import urlsplit
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse, Response
from starlette.middleware.gzip import GZipMiddleware
from starlette.concurrency import run_in_threadpool
from .api import router
from .storage import Store, meta
from .security import identity
from .validation import Problem, DEFAULT_PROFILE, timestamp
from .content import public_posts, visible_post, markdown, image_visible
from .git_activity import GitActivity

ROOT=Path(__file__).resolve().parents[1]
load_dotenv(ROOT/'.env',override=False)
logger=logging.getLogger('lin-notebook')


class Boundary:
    """Bound request bodies before parsing, including chunked transfer requests."""
    def __init__(self,app,store,production,site_url):
        self.app,self.store,self.production,self.site_url=app,store,production,site_url

    async def __call__(self,scope,receive,send):
        if scope['type']!='http': return await self.app(scope,receive,send)
        path=scope['path']; headers=dict(scope['headers']); method=scope['method']
        async def respond(status,message):
            await JSONResponse({'error':message},status_code=status)(scope,receive,secure_send)
        async def secure_send(message):
            if message['type']=='http.response.start':
                h=message.setdefault('headers',[])
                h.extend([(b'x-content-type-options',b'nosniff'),(b'referrer-policy',b'same-origin'),(b'x-frame-options',b'SAMEORIGIN' if path.startswith('/space-tools/') else b'DENY'),(b'content-security-policy',b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self' data:; frame-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'")])
                if path.startswith('/api') or path.startswith('/admin') or path.startswith('/space-tools'):
                    h[:]=[(k,v) for k,v in h if k.lower()!=b'cache-control']; h.append((b'cache-control',b'no-store'))
            await send(message)
        host=headers.get(b'host',b'').decode('latin1')
        if self.production and host!=urlsplit(self.site_url).netloc and host not in ('127.0.0.1:4317','localhost:4317'):
            return await respond(400,'无效主机名')
        if path.startswith('/api') and method not in ('GET','HEAD','OPTIONS') and path!='/api/ingest':
            origin=headers.get(b'origin',b'').decode('latin1')
            expected=self.site_url if self.production else scope['scheme']+'://'+host
            if origin!=expected: return await respond(403,'请求来源不匹配')
        req=Request(scope)
        token=req.cookies.get('space_session')
        def resolve_identity():
            with self.store.connect() as db: return identity(db,token)
        current=await run_in_threadpool(resolve_identity) if token else None
        scope.setdefault('state',{})['user']=current
        restricted=path.startswith(('/api/private/','/api/admin/','/api/studio/','/space-tools/'))
        if restricted:
            if not current: return await respond(401,'请先登录。')
            reader=path in ('/api/studio/profile','/api/studio/me','/api/studio/upload')
            if not reader and current['role']!='admin': return await respond(403,'此区域仅限站主管理员。')
        # Buffer only bounded API requests. No uploads can accumulate without limit.
        if method in ('POST','PUT','PATCH','DELETE'):
            maximum=12*1024*1024
            try:
                if int(headers.get(b'content-length',b'0'))>maximum: return await respond(413,'请求内容过大')
            except ValueError: return await respond(400,'请求长度无效')
            body=bytearray()
            try:
                async with asyncio.timeout(30):
                    while True:
                        message=await receive()
                        if message['type']=='http.disconnect': return
                        body.extend(message.get('body',b''))
                        if len(body)>maximum: return await respond(413,'请求内容过大')
                        if not message.get('more_body',False): break
            except TimeoutError: return await respond(408,'请求上传超时')
            delivered=False
            async def bounded_receive():
                nonlocal delivered
                if not delivered:
                    delivered=True; return {'type':'http.request','body':bytes(body),'more_body':False}
                return await receive()
            return await self.app(scope,bounded_receive,secure_send)
        await self.app(scope,receive,secure_send)


def create_app(data_dir=None,production=None,site_url=None,git_transport=None):
    production=(os.getenv('APP_ENV',os.getenv('NODE_ENV','development'))=='production') if production is None else production
    site_url=(site_url or os.getenv('SITE_URL','http://127.0.0.1:4317')).rstrip('/')
    if production and (urlsplit(site_url).scheme!='https' or urlsplit(site_url).path): raise RuntimeError('Production SITE_URL must be an HTTPS origin')
    store=Store(data_dir or os.getenv('DATA_DIR',ROOT/'data')); store.initialize()
    git=GitActivity(store,git_transport)
    @asynccontextmanager
    async def lifespan(app):
        yield
        await git.close()
    app=FastAPI(title='Lin Notebook',version='9.0.0',docs_url=None if production else '/api/docs',redoc_url=None,openapi_url=None if production else '/api/openapi.json',lifespan=lifespan)
    app.state.store=store; app.state.production=production; app.state.secure=production or os.getenv('COOKIE_SECURE')=='true'; app.state.git=git
    app.add_middleware(GZipMiddleware,minimum_size=1024)
    app.add_middleware(Boundary,store=store,production=production,site_url=site_url)
    @app.exception_handler(Problem)
    async def problem(request,error): return JSONResponse({'error':error.message,**error.extra},status_code=error.status)
    @app.exception_handler(RequestValidationError)
    async def validation(request,error): return JSONResponse({'error':'请求格式无效，请检查填写内容'},status_code=400)
    @app.exception_handler(sqlite3.IntegrityError)
    async def conflict(request,error): return JSONResponse({'error':'记录冲突，请刷新后重试'},status_code=409)
    @app.exception_handler(Exception)
    async def unexpected(request,error):
        logger.exception('Unhandled request error',exc_info=error)
        return JSONResponse({'error':'服务暂时无法完成请求，原有记录未被清空。'},status_code=500)
    app.include_router(router)
    from .backups import router as backups
    app.include_router(backups)

    @app.get('/healthz')
    def health():
        with store.connect() as db: db.execute('SELECT 1').fetchone()
        return {'ok':True,'version':'9.0.0'}

    @app.get('/uploads/{name}')
    def upload(request:Request,name:str):
        if not re.fullmatch(r'[\w-]+\.(png|jpeg|webp)',name,re.ASCII): return Response(status_code=404)
        with store.connect() as db:
            visible=image_visible(db,'/uploads/'+name); current=request.state.user
            row=db.execute('SELECT userId FROM upload_owners WHERE name=?',(name,)).fetchone()
            own=current and (current['role']=='admin' or (row and row['userId']==current['id']))
            dest=store.directory/'uploads'/name
            if not dest.is_file() or not (visible or own): return Response(status_code=404)
            return FileResponse(dest,headers={'Cache-Control':'public,max-age=60' if visible else 'private,no-store'})

    @app.get('/rss.xml')
    def rss():
        with store.connect() as db:
            p=meta(db,'profile',DEFAULT_PROFILE)
            items=''.join(f'<item><title>{escape(p["title"])}</title><link>{escape(site_url)}/blog/{p["slug"]}</link><guid>{escape(site_url)}/blog/{p["slug"]}</guid><description>{escape(p["excerpt"])}</description><pubDate>{formatdate(timestamp(p["publishAt"]),usegmt=True)}</pubDate></item>' for p in public_posts(db))
            return Response(f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{escape(p["name"])} 的博客</title><link>{escape(site_url)}</link><description>{escape(p["tagline"])}</description>{items}</channel></rss>',media_type='application/rss+xml')

    @app.get('/sitemap.xml')
    def sitemap():
        with store.connect() as db:
            items=''.join(f'<url><loc>{escape(site_url)}/blog/{p["slug"]}</loc><lastmod>{escape(p["updated"])}</lastmod></url>' for p in public_posts(db))
        return Response(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>{escape(site_url)}/</loc></url>{items}</urlset>',media_type='application/xml')

    @app.get('/robots.txt')
    def robots(): return PlainTextResponse('User-agent: *\nDisallow: /api/\nDisallow: /admin\nDisallow: /space-tools\nDisallow: /workspace\nDisallow: /studio\nSitemap: '+site_url+'/sitemap.xml')

    @app.api_route('/api/{path:path}',methods=['GET','POST','PUT','DELETE','PATCH','OPTIONS'])
    def missing_api(path:str): return JSONResponse({'error':'接口不存在'},status_code=404)

    @app.get('/{path:path}')
    def page(request:Request,path:str):
        if path in ('setup','login','account'): return RedirectResponse('/admin/account' if path=='account' else '/admin/login',302)
        if path=='workspace' or path.startswith('workspace/'):
            tool=path.partition('/')[2]
            return RedirectResponse('/admin/article/articleList' if tool=='writing' else '/admin/room' if tool in ('','home') else '/admin/life/'+tool,302)
        if path=='studio' or path.startswith('studio/'):
            target={'comments':'comments','users':'authors','settings':'site-settings','posts':'article/articleList'}.get(path.partition('/')[2],'home')
            return RedirectResponse('/admin/'+target,302)
        if path.startswith('space-tools/'):
            if path.partition('/')[2] not in ('tasks','calendar','habits','health','sleep','library','review','settings'): return Response(status_code=404)
            entry=ROOT/'public/tools-app/index.html'; restricted=True
        elif path=='admin' or path.startswith('admin/'):
            entry=ROOT/'public/admin-app/index.html'; restricted=True
        elif path in ('','home','moments','albums','blog','about','archive','archives','category','categories','tag','article','articleList') or re.fullmatch('blog/[a-z0-9][a-z0-9-]{0,100}',path):
            entry=ROOT/'public/blog-app/index.html'; restricted=False
        else:
            # Static allowlist, never expose source, manifests, configuration or HTML entries.
            if path=='admin-app/serverConfig.json':
                return FileResponse(ROOT/'public/admin-app/serverConfig.json',headers={'Cache-Control':'no-cache'})
            if path in ('licenses/blog-admin-MIT.txt','licenses/PureAdmin-MIT.txt','licenses/vue3-blog-MIT.txt'):
                return FileResponse(ROOT/'public'/path,media_type='text/plain',headers={'Cache-Control':'public,max-age=3600'})
            allowed=path.startswith(('blog-app/assets/','admin-app/assets/','tools-app/assets/','assets/','audio/','fonts/')) or path in {'favicon.svg','lin-icons.svg','fonts.css','styles.css','v2.css','workbench.css','space-tools.css'}
            dest=(ROOT/'public'/path).resolve()
            if not allowed or not dest.is_relative_to((ROOT/'public').resolve()) or dest.suffix not in ('.js','.css','.svg','.png','.jpeg','.jpg','.webp','.woff','.woff2','.ttf','.mp3','.ogg','.wav') or not dest.is_file(): return Response(status_code=404)
            immutable=path.startswith(('blog-app/assets/','admin-app/assets/','tools-app/assets/'))
            return FileResponse(dest,headers={'Cache-Control':'public,max-age=31536000,immutable' if immutable else 'public,max-age=3600' if dest.suffix not in ('.js','.css') else 'no-cache'})
        if not entry.is_file(): return PlainTextResponse('Frontend build missing. Run npm run build.',503)
        html=entry.read_text(encoding='utf-8'); code=200
        with store.connect() as db:
            profile=meta(db,'profile',DEFAULT_PROFILE); settings=meta(db,'site',{})
            slug=path[5:] if path.startswith('blog/') else request.query_params.get('id') if path=='article' else None
            p=None
            if slug:
                try: p=visible_post(db,slug)
                except Problem as error:
                    if error.status!=404: raise
            posts=public_posts(db) if not restricted and not slug else []
            if slug and not p: code=404
            title=(p['title']+' · ' if p else '')+(settings.get('title') or profile['name'])
            description=p['excerpt'] if p else settings.get('subtitle') or profile['tagline']
            tags=f'<title>{escape(title)}</title><meta name="description" content="{escape(description)}"><meta property="og:title" content="{escape(title)}"><link rel="canonical" href="{escape(site_url+request.url.path)}">'
            if restricted: tags+='<meta name="robots" content="noindex,nofollow">'
            ssr='' if restricted else f'<article><h1>{escape(p["title"])}</h1>{markdown(p["content"])["html"]}</article>' if p else '<h1>'+escape(title)+'</h1>'+''.join(f'<article><h2><a href="/blog/{p["slug"]}">{escape(p["title"])}</a></h2><p>{escape(p["excerpt"])}</p></article>' for p in posts)
        return HTMLResponse(html.replace('<!--META-->',tags).replace('<!--SSR-->',ssr),status_code=code,headers={'Cache-Control':'no-store'})
    return app
