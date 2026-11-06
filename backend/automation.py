"""Fixed-template personal automations. Durable queue; no arbitrary code or URLs."""
import asyncio
import io
import ipaddress
import json
import logging
import re
import socket
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from PIL import Image
from fastapi import APIRouter, Request, Query

from .storage import stamp, dumps, meta, set_meta, audit
from .validation import text, number, choice, fail
from .content import insert, records

router=APIRouter(prefix='/api/private/automation')
log=logging.getLogger('lin-notebook.automation')
TEMPLATES={
    'seasonal-anime':{'name':'季度新番收藏','steps':['固定 Yuciwiki 季度来源','解析、去重与封面缩略图','私人预览与确认','保存文档 / 收藏 / 邮件'],'execution':'cloud'},
    'weekly-review':{'name':'个人空间周报','steps':['读取本站近期文章与生活统计','生成私人周报','私人预览与确认','保存文档 / 邮件'],'execution':'cloud'},
    'local-digest':{'name':'本地 AI 资料收件箱','steps':['本地浏览器或 AI 处理资料','受限 Token 提交结构化结果','私人预览与确认','保存文档 / 邮件'],'execution':'local'},
}


def validate_config(template,body):
    if not isinstance(body,dict): fail(400,'任务参数必须是对象')
    c={'schedule':choice(body.get('schedule','manual'),['manual','daily','weekly','quarterly']),
       'sendTime':text(body.get('sendTime','09:00'),5,5),'timezone':text(body.get('timezone','Asia/Shanghai'),80,1),
       'weekday':number(body.get('weekday',0),0,6,True),'saveDocument':body.get('saveDocument',True),
       'saveLibrary':body.get('saveLibrary',False),'email':body.get('email',False),
       'quarter':text(body.get('quarter','auto'),6,4),'limit':number(body.get('limit',0),0,200,True)}
    if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',c['sendTime']): fail(400,'发送时间格式无效')
    try: ZoneInfo(c['timezone'])
    except Exception: fail(400,'时区无效')
    if c['quarter']!='auto' and not re.fullmatch(r'20\d{2}(01|04|07|10)',c['quarter']): fail(400,'季度格式应为 202610 或 auto')
    if c['quarter']!='auto' and c['quarter']<'202407': fail(400,'支持从 2024 年 7 月开始的季度')
    if any(not isinstance(c[k],bool) for k in ('saveDocument','saveLibrary','email')): fail(400,'输出开关必须是布尔值')
    if template!='seasonal-anime' and c['saveLibrary']: fail(400,'只有新番流程可保存到番剧收藏')
    if template=='local-digest' and c['schedule']!='manual': fail(400,'本地资料由执行器主动提交，不使用云端定时')
    if not any(c[k] for k in ('saveDocument','saveLibrary','email')): fail(400,'至少选择一个输出目标')
    return c


def flow_row(row):
    return {**dict(row),'config':json.loads(row['config']),'enabled':bool(row['enabled'])}


def run_row(row):
    return {k:row[k] for k in ('id','flowId','state','error','attempts','created','updated')} | {'snapshot':json.loads(row['snapshot']),'result':json.loads(row['result'])}


def enqueue(db,flow,key):
    existing=db.execute('SELECT * FROM automation_runs WHERE requestKey=?',(key,)).fetchone()
    if existing: return run_row(existing)
    if db.execute("SELECT count(*) FROM automation_runs WHERE state IN ('queued','running')").fetchone()[0]>=10: fail(429,'待运行任务已达上限')
    identifier=str(uuid4());now=stamp()
    db.execute('INSERT INTO automation_runs(id,flowId,snapshot,state,requestKey,created,updated) VALUES(?,?,?,?,?,?,?)',
        (identifier,flow['id'],dumps(flow),'queued',key,now,now))
    audit(db,'automation:enqueue',identifier)
    return run_row(db.execute('SELECT * FROM automation_runs WHERE id=?',(identifier,)).fetchone())


class SourceParser(HTMLParser):
    """Parse only known Yuciwiki title and broadcast classes, not source HTML."""
    def __init__(self):
        super().__init__(convert_charrefs=True);self.items=[];self.item=None;self.field=None;self.depth=0
    def handle_comment(self,data):
        if re.fullmatch(r'#[A-Z]\d{2,3}',data.strip()):
            if self.item and self.item.get('title'): self.items.append(self.item)
            self.item={'sourceId':data.strip()[1:],'title':'','subtitle':'','tags':'','broadcast':'','coverSource':''}
    def handle_starttag(self,tag,attrs):
        if self.item is None:return
        a=dict(attrs);cls=a.get('class','')
        if tag=='img' and not self.item['coverSource']: self.item['coverSource']=a.get('data-src',a.get('src',''))
        for name,prefix in [('title','title_cn'),('subtitle','title_jp'),('tags','type_tag'),('broadcast','broadcast_')]:
            if cls.startswith(prefix): self.field=name;self.depth=1;return
        if self.field:self.depth+=1
    def handle_endtag(self,tag):
        if self.field:
            self.depth-=1
            if self.depth<=0:self.field=None
    def handle_data(self,data):
        if self.field and self.item is not None:self.item[self.field]+=data
    def finish(self):
        if self.item and self.item.get('title'):self.items.append(self.item)
        return [{k:v.strip()[:500] for k,v in item.items()} for item in self.items if item['title'].strip()]


def parse_season(raw,quarter):
    p=SourceParser();p.feed(raw);items=p.finish();seen=set();result=[]
    for item in items:
        key=f'yuc:{quarter}:{item["sourceId"]}'
        if key in seen:continue
        seen.add(key);result.append({**item,'sourceKey':key,'url':f'https://yuc.wiki/{quarter}/#{item["sourceId"]}'})
    if not result:raise ValueError('来源页面结构已变化或没有季度内容，未生成伪造结果')
    return result


def allowed_url(url,image=False):
    p=urlsplit(url)
    if p.scheme!='https' or p.username or p.password or p.port not in (None,443) or p.fragment:raise ValueError('来源 URL 不在允许范围')
    if image:
        ok=p.hostname in ('i0.hdslb.com','i1.hdslb.com','i2.hdslb.com') and p.path.startswith('/bfs/') and not p.query
    else:ok=p.hostname=='yuc.wiki' and re.fullmatch(r'/20\d{2}(01|04|07|10)/',p.path) and not p.query
    if not ok:raise ValueError('来源 URL 不在允许范围')
    return p


def bounded_fetch(url,maximum,image=False,transport=None):
    p=allowed_url(url,image)
    if transport is None:
        addresses=socket.getaddrinfo(p.hostname,443,type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):raise ValueError('拒绝访问内网地址')
    with httpx.Client(timeout=httpx.Timeout(8,connect=4),follow_redirects=False,trust_env=False,transport=transport) as client:
        with client.stream('GET',url,headers={'User-Agent':'PersonalSpace/10 (+private seasonal reading)','Accept':'image/*' if image else 'text/html'}) as response:
            response.raise_for_status()
            if response.is_redirect:raise ValueError('不跟随来源重定向')
            kind=response.headers.get('content-type','').lower()
            if image and not kind.startswith('image/'):raise ValueError('封面不是图片')
            if not image and 'text/html' not in kind:raise ValueError('来源不是 HTML')
            raw=bytearray()
            started=time.monotonic()
            for block in response.iter_bytes():
                raw.extend(block)
                if len(raw)>maximum or time.monotonic()-started>12:raise ValueError('来源超过大小或时间限制')
            return bytes(raw)


def thumbnail(store,url):
    raw=bounded_fetch(url,2*1024*1024,True)
    from .security import validate_image
    with Image.open(io.BytesIO(raw)) as img: extension=img.format.lower()
    validate_image(raw,extension)
    with Image.open(io.BytesIO(raw)) as img:
        img=img.convert('RGB');img.thumbnail((360,520));out=io.BytesIO();img.save(out,format='WEBP',quality=78)
    name=str(uuid4())+'.webp';dest=store.directory/'uploads'/name
    try:
        dest.write_bytes(out.getvalue())
        with store.transaction() as db:db.execute("INSERT INTO upload_owners VALUES(?,'owner')",(name,))
    except BaseException:dest.unlink(missing_ok=True);raise
    return '/uploads/'+name


def collect(store,flow):
    c=flow['config'];now=datetime.now(ZoneInfo(c['timezone']))
    if flow['template']=='weekly-review':
        from .mailing import report,report_text
        with store.connect() as db:
            data=report(db);tasks=records(db,'tasks');notes=records(db,'notes')
        return {'title':'个人空间周报 · '+now.date().isoformat(),'text':report_text(data,'')+'\n\n生活记录：\n'+f'任务 {len(tasks)} 项，其中完成 {sum(t.get("status")=="done" for t in tasks)} 项；日志 {len(notes)} 条（总量统计）。','items':[],'warnings':[]}
    if flow['template']=='local-digest':return {'title':'等待本地资料','text':'请通过本地 AI Access Token 提交资料。','items':[],'warnings':[]}
    quarter=c['quarter'] if c['quarter']!='auto' else f'{now.year}{(now.month-1)//3*3+1:02d}'
    key='season:'+quarter
    with store.connect() as db:cache=db.execute('SELECT * FROM connector_cache WHERE key=?',(key,)).fetchone()
    if cache and cache['updated']>int(time.time())-21600:
        all_items=json.loads(cache['data'])
    else:
        source=bounded_fetch(f'https://yuc.wiki/{quarter}/',2*1024*1024).decode('utf-8')
        all_items=parse_season(source,quarter)
        with store.transaction() as db:db.execute('INSERT INTO connector_cache VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET data=excluded.data,updated=excluded.updated',(key,dumps(all_items),int(time.time())))
    items=[dict(item) for item in (all_items[:c['limit']] if c['limit'] else all_items[:200])];warnings=[]
    if not c['limit'] and len(all_items)>200: warnings.append('来源超过 200 条，本次保留前 200 条')
    for item in items:item['cover']=''
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(thumbnail,store,item['coverSource']):item for item in items if item['coverSource']}
        done,pending=wait(futures,timeout=75)
        for future in pending:future.cancel()
        if pending:warnings.append('封面处理达到时间预算，部分条目保留来源链接')
    for future,item in futures.items():
        if future.cancelled():continue
        try:item['cover']=future.result()
        except Exception: warnings.append(item['title']+'：封面未能保存，保留来源链接')
    lines=[f'# {quarter} 季度新番','',f'来源：https://yuc.wiki/{quarter}/','',f'读取 {len(all_items)} 条，按设置预览前 {len(items)} 条。','']
    for item in items:lines.extend([f'## {item["title"]}',item['subtitle'],item['tags'],item['broadcast'],item['url'],''])
    return {'title':quarter+' 季度新番','text':'\n'.join(lines),'items':items,'warnings':warnings,'sourceCount':len(all_items),'source':f'https://yuc.wiki/{quarter}/'}


def process_one(store):
    now=int(time.time())
    with store.transaction() as db:
        db.execute("UPDATE automation_runs SET state=CASE WHEN attempts<2 THEN 'queued' ELSE 'failed' END,error='执行租约过期，已恢复或停止',leaseUntil=0 WHERE state='running' AND leaseUntil<?",(now,))
        row=db.execute("SELECT * FROM automation_runs WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
        if not row:return
        db.execute("UPDATE automation_runs SET state='running',leaseUntil=?,attempts=attempts+1,updated=? WHERE id=?",(now+180,stamp(),row['id']))
    flow=json.loads(row['snapshot'])
    try:
        result=collect(store,flow)
        state='waiting_executor' if flow['template']=='local-digest' else 'waiting_approval';error=''
    except Exception as exc:
        result={};state='failed';error='来源读取或解析失败，请检查来源是否可用后重试（'+type(exc).__name__+'）'
        log.warning('Automation source failed: %s',type(exc).__name__)
    with store.transaction() as db:db.execute("UPDATE automation_runs SET state=?,result=?,error=?,leaseUntil=0,updated=? WHERE id=? AND state='running'",(state,dumps(result),error,stamp(),row['id']))


def schedule_tick(store,now=None):
    with store.transaction() as db:
        if meta(db,'automationPaused',False):return
        for row in db.execute('SELECT * FROM automation_flows WHERE enabled=1'):
            flow=flow_row(row);c=flow['config'];n=now or datetime.now(ZoneInfo(c['timezone']));n=n.astimezone(ZoneInfo(c['timezone']))
            if c['schedule']=='manual' or n.strftime('%H:%M')<c['sendTime']:continue
            if c['schedule']=='weekly' and n.weekday()!=c['weekday']:continue
            if c['schedule']=='quarterly' and not (n.day==1 and n.month in (1,4,7,10)):continue
            slot=n.strftime('%Y-%m-%d')
            enqueue(db,flow,'scheduled:'+flow['id']+':'+slot)


async def worker(app):
    while True:
        try:
            await asyncio.to_thread(schedule_tick,app.state.store)
            with app.state.store.connect() as db:paused=meta(db,'automationPaused',False)
            if not paused:await asyncio.to_thread(process_one,app.state.store)
        except asyncio.CancelledError:raise
        except Exception:log.exception('Automation worker tick failed')
        await asyncio.sleep(3)


@router.get('')
def overview(request:Request,compact:bool=False):
    with request.app.state.store.connect() as db:
        runs=run_summaries(db,1,50)['items'] if compact else [run_row(r) for r in db.execute('SELECT * FROM automation_runs ORDER BY created DESC LIMIT 50')]
        return {'templates':TEMPLATES,'paused':meta(db,'automationPaused',False),'flows':[flow_row(r) for r in db.execute('SELECT * FROM automation_flows ORDER BY created DESC')],'runs':runs}


def run_summaries(db,page,page_size,state='',flow_id=''):
    from .experience import page_result
    where=['1=1'];args=[]
    if state:
        choice(state,['queued','running','waiting_approval','waiting_executor','succeeded','failed','canceled','sending','email_pending','delivery_failed','delivery_unknown'])
        where.append('state=?');args.append(state)
    if flow_id:where.append('flowId=?');args.append(flow_id)
    condition=' AND '.join(where)
    total=db.execute('SELECT count(*) FROM automation_runs WHERE '+condition,args).fetchone()[0]
    # The large result JSON never leaves SQLite on a summary request.
    rows=db.execute('SELECT id,flowId,state,error,created,updated,json_extract(snapshot,\'$.name\') AS name FROM automation_runs WHERE '+condition+' ORDER BY created DESC,id DESC LIMIT ? OFFSET ?',[*args,page_size,(page-1)*page_size])
    return page_result([dict(r) for r in rows],total,page,page_size)


@router.get('/runs')
def list_runs(request:Request,page:int=Query(1,ge=1,le=100000),pageSize:int=Query(20,ge=1,le=100),state:str='',flowId:str=Query('',max_length=80)):
    with request.app.state.store.connect() as db:return run_summaries(db,page,pageSize,state,flowId)


@router.get('/runs/{identifier}')
def read_run(request:Request,identifier:str):
    with request.app.state.store.connect() as db:
        row=db.execute('SELECT * FROM automation_runs WHERE id=?',(identifier,)).fetchone()
        if not row:fail(404,'运行不存在')
        return run_row(row)


@router.put('/pause')
def pause(request:Request,body:dict):
    if not isinstance(body.get('paused'),bool):fail(400,'暂停开关无效')
    with request.app.state.store.transaction() as db:set_meta(db,'automationPaused',body['paused']);audit(db,'automation:pause')
    return {'paused':body['paused']}


@router.post('/flows',status_code=201)
def create_flow(request:Request,body:dict):
    template=choice(body.get('template'),TEMPLATES);name=text(body.get('name'),100,1,True);config=validate_config(template,body.get('config',{}));now=stamp();identifier=str(uuid4())
    with request.app.state.store.transaction() as db:
        if db.execute('SELECT count(*) FROM automation_flows').fetchone()[0]>=30:fail(400,'最多创建 30 个任务')
        db.execute('INSERT INTO automation_flows VALUES(?,?,?,?,0,1,?,?)',(identifier,name,template,dumps(config),now,now));audit(db,'automation:create',identifier)
        return flow_row(db.execute('SELECT * FROM automation_flows WHERE id=?',(identifier,)).fetchone())


@router.put('/flows/{identifier}')
def edit_flow(request:Request,identifier:str,body:dict):
    with request.app.state.store.transaction() as db:
        row=db.execute('SELECT * FROM automation_flows WHERE id=?',(identifier,)).fetchone()
        if not row:fail(404,'任务不存在')
        if body.get('version')!=row['version']:fail(409,'任务已更新，请刷新')
        enabled=body.get('enabled',False)
        if not isinstance(enabled,bool):fail(400,'启用开关无效')
        config=validate_config(row['template'],body.get('config',{}));name=text(body.get('name'),100,1,True)
        db.execute('UPDATE automation_flows SET name=?,config=?,enabled=?,version=version+1,updated=? WHERE id=?',(name,dumps(config),int(enabled),stamp(),identifier));audit(db,'automation:update',identifier)
        return flow_row(db.execute('SELECT * FROM automation_flows WHERE id=?',(identifier,)).fetchone())


@router.delete('/flows/{identifier}')
def delete_flow(request:Request,identifier:str,body:dict):
    with request.app.state.store.transaction() as db:
        row=db.execute('SELECT version FROM automation_flows WHERE id=?',(identifier,)).fetchone()
        if not row:fail(404,'任务不存在')
        if body.get('version')!=row['version']:fail(409,'任务已更新，请刷新')
        if db.execute("SELECT 1 FROM automation_runs WHERE flowId=? AND state IN ('queued','running','email_pending','sending')",(identifier,)).fetchone():fail(409,'任务正在运行或投递，请稍后删除')
        db.execute('DELETE FROM automation_flows WHERE id=?',(identifier,));audit(db,'automation:delete',identifier)
    return {'ok':True}


@router.post('/flows/{identifier}/run',status_code=202)
def trigger(request:Request,identifier:str,body:dict):
    from .security import rate
    with request.app.state.store.transaction() as db:
        if meta(db,'automationPaused',False):fail(409,'自动化已暂停')
        rate(db,'owner','automation-trigger',12,600)
        row=db.execute('SELECT * FROM automation_flows WHERE id=?',(identifier,)).fetchone()
        if not row:fail(404,'任务不存在')
        return enqueue(db,flow_row(row),'manual:'+identifier+':'+text(body.get('key'),100,1))


@router.post('/runs/{identifier}/cancel')
def cancel(request:Request,identifier:str):
    with request.app.state.store.transaction() as db:
        row=db.execute('SELECT state FROM automation_runs WHERE id=?',(identifier,)).fetchone()
        if not row:fail(404,'运行不存在')
        if row['state'] not in ('queued','running','waiting_approval','waiting_executor','failed'):fail(409,'当前运行不可取消')
        db.execute("UPDATE automation_runs SET state='canceled',updated=? WHERE id=?",(stamp(),identifier));audit(db,'automation:cancel',identifier)
    return {'ok':True}


@router.post('/runs/{identifier}/approve')
def approve(request:Request,identifier:str):
    with request.app.state.store.transaction() as db:
        row=db.execute('SELECT * FROM automation_runs WHERE id=?',(identifier,)).fetchone()
        if not row:fail(404,'运行不存在')
        if row['state']=='succeeded':return run_row(row)
        if row['state']!='waiting_approval':fail(409,'仅待确认结果可保存')
        result=json.loads(row['result']);flow=json.loads(row['snapshot']);c=flow['config'];now=stamp()
        if c['saveDocument']:
            document=str(uuid4());db.execute('INSERT INTO private_documents(id,title,category,content,created,updated) VALUES(?,?,?,?,?,?)',(document,result['title'][:180],'自动化',result['text'],now,now));result['documentId']=document
        added=0
        if c['saveLibrary']:
            from .validation import validate_record
            for item in result.get('items',[]):
                if db.execute('SELECT 1 FROM automation_items WHERE sourceKey=?',(item['sourceKey'],)).fetchone():continue
                data=validate_record('library',{'title':item['title'][:200],'kind':'番剧','status':'wish','progress':0,'total':12,'cover':item.get('cover') or '/assets/flower-03.webp','note':item['url']+'\n'+item['broadcast']+'\n集数为待确认默认值，请按实际调整。','tags':item['tags']})
                quarter=item.get('sourceKey','').split(':')[1] if item.get('sourceKey','').startswith('yuc:') else c.get('quarter','')
                if re.fullmatch(r'[0-9]{6}',quarter): data['season']=quarter[:4]+'-Q'+str((int(quarter[4:])-1)//3+1)
                data['broadcast']=item.get('broadcast','')[:100]
                saved=insert(db,'library',data);db.execute('INSERT INTO automation_items VALUES(?,?,?)',(item['sourceKey'],saved['id'],now));added+=1
        result['added']=added
        state='email_pending' if c['email'] else 'succeeded'
        db.execute('UPDATE automation_runs SET state=?,result=?,updated=? WHERE id=?',(state,dumps(result),now,identifier));audit(db,'automation:approve',identifier)
    if c['email']:deliver_result(request.app.state.store,identifier)
    with request.app.state.store.connect() as db:return run_row(db.execute('SELECT * FROM automation_runs WHERE id=?',(identifier,)).fetchone())


def deliver_result(store,identifier):
    from .mailing import send_email,DeliveryUnknown,connection_error
    # Claim before SMTP; a crash cannot automatically resend an ambiguous delivery.
    with store.transaction() as db:
        row=db.execute("SELECT * FROM automation_runs WHERE id=? AND state='email_pending'",(identifier,)).fetchone()
        if not row:return
        db.execute("UPDATE automation_runs SET state='sending',updated=? WHERE id=?",(stamp(),identifier))
        result=json.loads(row['result']);config=meta(db,'mailSettings',{});mail_id=str(uuid4())
        db.execute('INSERT INTO email_runs(id,kind,status,subject,recipient,created) VALUES(?,?,?,?,?,?)',(mail_id,'automation','sending',result['title'],config.get('recipient',''),stamp()))
    try:send_email(config,result['title'],result['text']);state='succeeded';mail_state='succeeded';error=''
    except DeliveryUnknown:state='delivery_unknown';mail_state='unknown';error='邮件投递结果未知，请先检查收件箱，不自动重发'
    except Exception as exc:state='delivery_failed';mail_state='failed';error=connection_error(exc)
    with store.transaction() as db:
        db.execute('UPDATE email_runs SET status=?,finished=?,error=? WHERE id=?',(mail_state,stamp(),error,mail_id))
        db.execute('UPDATE automation_runs SET state=?,error=?,updated=? WHERE id=?',(state,error,stamp(),identifier))


def recover_delivery(store):
    with store.transaction() as db:db.execute("UPDATE automation_runs SET state='delivery_unknown',error='重启前投递结果未知，请检查邮箱',updated=? WHERE state IN ('sending','email_pending')",(stamp(),))


@router.post('/runs/{identifier}/retry-email')
def retry_email(request:Request,identifier:str):
    with request.app.state.store.transaction() as db:
        row=db.execute('SELECT state FROM automation_runs WHERE id=?',(identifier,)).fetchone()
        if not row:fail(404,'运行不存在')
        if row['state']!='delivery_failed':fail(409,'只有明确失败的投递可重试')
        db.execute("UPDATE automation_runs SET state='email_pending',updated=? WHERE id=?",(stamp(),identifier))
    deliver_result(request.app.state.store,identifier)
    with request.app.state.store.connect() as db:return run_row(db.execute('SELECT * FROM automation_runs WHERE id=?',(identifier,)).fetchone())
