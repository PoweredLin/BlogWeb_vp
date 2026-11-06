"""Private external documentation bookmarks; no reverse proxy or HTML import."""
from urllib.parse import urlsplit
from fastapi import APIRouter, Request
from .storage import meta,set_meta,audit
from .validation import text,fail,number

router=APIRouter(prefix='/api/private/reference-docs')
EMBED_ORIGINS=('https://fastapi.tiangolo.com','https://vite.dev','https://www.typescriptlang.org')
DEFAULTS=[
    {'id':'vue','title':'Vue 3 中文文档','url':'https://cn.vuejs.org/guide/introduction.html','tags':'Vue,前端','description':'源站限制 iframe，使用新标签页。'},
    {'id':'fastapi','title':'FastAPI 中文文档','url':'https://fastapi.tiangolo.com/zh/','tags':'Python,后端','description':'本站后端框架。'},
    {'id':'vite','title':'Vite 指南','url':'https://vite.dev/guide/','tags':'构建,前端','description':'前端构建与开发指南。'},
    {'id':'typescript','title':'TypeScript Handbook','url':'https://www.typescriptlang.org/docs/','tags':'TypeScript,前端','description':'类型系统与语言手册。'},
    {'id':'mdn','title':'MDN Web Docs','url':'https://developer.mozilla.org/zh-CN/docs/Web','tags':'Web,参考','description':'源站明确禁止 iframe，使用新标签页。'},
    {'id':'mermaid','title':'Mermaid 图表语法','url':'https://mermaid.js.org/intro/syntax-reference.html','tags':'文档,流程图','description':'流程图语法与示例。'},
]


def normalize(rows):
    if not isinstance(rows,list) or len(rows)>50:fail(400,'最多保存 50 个文档书签')
    result=[];ids=set()
    for item in rows:
        if not isinstance(item,dict):fail(400,'书签格式无效')
        identifier=text(item.get('id'),80,1,True);url=text(item.get('url'),1000,1,True);p=urlsplit(url)
        try:port=p.port
        except ValueError:fail(400,'文档地址无效')
        if p.scheme!='https' or not p.hostname or p.username or p.password or port not in (None,443) or '.' not in p.hostname or '\\' in url or any(c.isspace() for c in url):fail(400,'文档地址须为标准 HTTPS 公网地址')
        if identifier in ids:fail(400,'书签 ID 重复')
        public=item.get('public',False)
        if not isinstance(public,bool):fail(400,'书签公开开关无效')
        ids.add(identifier);result.append({'id':identifier,'title':text(item.get('title'),100,1,True),'url':url,'tags':text(item.get('tags',''),200),'description':text(item.get('description',''),500),'public':public})
    return result


@router.get('')
def get_docs(request:Request):
    with request.app.state.store.connect() as db:
        value=meta(db,'referenceDocs',{'version':1,'items':DEFAULTS})
        return {**value,'items':[{**item,'embeddable':urlsplit(item['url']).scheme+'://'+urlsplit(item['url']).netloc in EMBED_ORIGINS} for item in value['items']],'recent':meta(db,'referenceRecent',[]) ,'embedOrigins':EMBED_ORIGINS}


@router.put('')
def save_docs(request:Request,body:dict):
    rows=normalize(body.get('items'))
    with request.app.state.store.transaction() as db:
        old=meta(db,'referenceDocs',{'version':1})
        if body.get('version')!=old['version']:fail(409,'书架已更新，请刷新')
        set_meta(db,'referenceDocs',{'version':old['version']+1,'items':rows});audit(db,'reference-docs:update')
    return get_docs(request)


@router.post('/visit')
def visit(request:Request,body:dict):
    identifier=text(body.get('id'),80,1)
    with request.app.state.store.transaction() as db:
        allowed=meta(db,'referenceDocs',{'items':DEFAULTS})['items']
        if not any(item['id']==identifier for item in allowed):fail(404,'文档书签不存在')
        recent=[identifier]+[key for key in meta(db,'referenceRecent',[]) if key!=identifier]
        set_meta(db,'referenceRecent',recent[:10])
    return {'ok':True}
