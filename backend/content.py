import copy
import json
import math
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from markdown_it import MarkdownIt
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter
from pygments.util import ClassNotFound
from html import escape
from functools import lru_cache
from .storage import meta, set_meta, stamp, dumps, record, audit
from .security import millis, check_images
from .validation import DEFAULT_PROFILE, DEFAULT_STORY, SITE_DEFAULTS, PROFILE_DEFAULTS, validate_record, fail, timestamp


def day(): return (datetime.now(timezone.utc)+timedelta(hours=8)).date().isoformat()


def code_highlight(code,language,*args):
    try: inner=highlight(code,get_lexer_by_name(language),HtmlFormatter(nowrap=True))
    except ClassNotFound: inner=escape(code)
    return '<pre class="hljs"><code>'+inner+'</code></pre>'


md=MarkdownIt('default',{'html':False,'linkify':True,'typographer':True,'highlight':code_highlight})


@lru_cache(maxsize=64)
def markdown(content):
    tokens=md.parse(content); headings=[]
    for i,token in enumerate(tokens):
        if token.type=='heading_open':
            identifier='section-'+str(len(headings)+1); token.attrSet('id',identifier)
            headings.append({'id':identifier,'text':tokens[i+1].content,'level':token.tag})
    return {'html':md.renderer.render(tokens,md.options,{}),'headings':headings}


def profile(db,user):
    row=db.execute('SELECT * FROM member_profiles WHERE userId=?',(user['id'],)).fetchone()
    life=meta(db,'profile' if user['id']=='owner' else 'user:'+user['id']+':profile',{})
    return {**PROFILE_DEFAULTS,**(json.loads(row['data']) if row else {}),'name':user['name'],'wallpaper':life.get('wallpaper','landscape-study'),'version':row['version'] if row else 1}


def site(db):
    result={**SITE_DEFAULTS,**meta(db,'site',{})}
    if result['heroTail']=='的随记': result['heroTail']=''
    return result


def author(db,uid):
    row=db.execute('SELECT data FROM member_profiles WHERE userId=?',(uid,)).fetchone()
    p=json.loads(row['data']) if row else {}
    if uid=='owner': name=meta(db,'profile',DEFAULT_PROFILE)['name']
    else:
        user=db.execute('SELECT name FROM users WHERE id=?',(uid,)).fetchone(); name=user['name'] if user else '作者'
    return {'authorName':name,'authorAvatar':p.get('avatar','/favicon.svg'),'authorBio':p.get('bio','')}


def records(db,kind,uid=None):
    query='SELECT * FROM records WHERE kind=? AND deleted IS NULL'
    args=[kind]
    if uid: query+=' AND userId=?'; args.append(uid)
    return [record(r) for r in db.execute(query+' ORDER BY created DESC,id',args)]


def public_posts(db):
    result=[]; authors={}
    for r in db.execute("SELECT * FROM records WHERE kind='posts' AND deleted IS NULL AND json_extract(data,'$.status') IN ('published','scheduled')"):
        p=record(r)
        if p.get('status') in ('published','scheduled') and timestamp(p['publishAt'])<=millis()/1000:
            uid=r['userId']
            if uid not in authors: authors[uid]=author(db,uid)
            result.append({**p,**authors[uid]})
    return sorted(result,key=lambda p:timestamp(p['publishAt']),reverse=True)


def visible_post(db,slug):
    row=db.execute("SELECT * FROM records WHERE kind='posts' AND deleted IS NULL AND json_extract(data,'$.slug')=?",(slug,)).fetchone()
    post=record(row)
    if not post or post.get('status') not in ('published','scheduled') or timestamp(post['publishAt'])>millis()/1000: fail(404,'文章不存在或尚未公开')
    return {**post,**author(db,row['userId'])}


def taxonomy(db):
    return {kind:[r['name'] for r in db.execute('SELECT name FROM taxonomy WHERE kind=? ORDER BY name',(kind,))] for kind in ('categories','tags')}


def add_taxonomy(db,data):
    for kind,names in [('categories',[data['category']]),('tags',data.get('tags','').split(','))]:
        for name in names:
            if name: db.execute('INSERT OR IGNORE INTO taxonomy VALUES(?,?)',(kind,name))


def insert(db,kind,data,identifier=None,uid='owner'):
    identifier=identifier or str(uuid4()); time=stamp()
    db.execute('INSERT INTO records(id,kind,data,created,updated,userId) VALUES(?,?,?,?,?,?)',(identifier,kind,dumps(data),time,time,uid))
    audit(db,'create:'+kind,identifier,uid)
    return record(db.execute('SELECT * FROM records WHERE id=?',(identifier,)).fetchone())


def unlock(db,key):
    s=meta(db,'story',copy.deepcopy(DEFAULT_STORY)); s['unlocks'].setdefault(key,millis()); set_meta(db,'story',s)


def unique(db,kind,data,identifier=''):
    if kind=='posts' and db.execute("SELECT id FROM records WHERE kind='posts' AND deleted IS NULL AND json_extract(data,'$.slug')=? AND id<>?",(data['slug'],identifier)).fetchone(): fail(409,'文章链接已被使用，请换一个链接名')
    if kind in ('health','sleep','notes') and any(r['date']==data['date'] and r['id']!=identifier for r in records(db,kind,'owner')): fail(409,'这一天已有记录，请编辑已有记录')


def save(db,kind,body,identifier=None):
    data=validate_record(kind,body); check_images(db,data,'owner')
    if kind=='posts': add_taxonomy(db,data)
    if not identifier and body.get('clientId'):
        try: UUID(body['clientId'])
        except (ValueError,TypeError,AttributeError): fail(400,'创建标识无效')
        previous=db.execute('SELECT * FROM records WHERE id=?',(body['clientId'],)).fetchone()
        if previous:
            if previous['userId']!='owner': fail(409,'创建标识不可用')
            if previous['kind']==kind and not previous['deleted'] and validate_record(kind,json.loads(previous['data']))==data: return record(previous)
            fail(409,'创建请求已保存不同内容',current=record(previous),submitted=data)
    unique(db,kind,data,identifier or '')
    if identifier:
        old=db.execute('SELECT * FROM records WHERE id=? AND kind=? AND deleted IS NULL',(identifier,kind)).fetchone()
        if not old or old['userId']!='owner': fail(404,'记录不存在')
        if body.get('version')!=old['version']: fail(409,'记录已更新，请刷新后重试',current=record(old),submitted=data)
        previous=json.loads(old['data'])
        for key in ('source','receivedAt','idempotencyKey'):
            if key in previous: data[key]=previous[key]
        if kind=='habits':
            for date in previous['checks'].keys()|data['checks'].keys():
                if date!=day() and previous['checks'].get(date,0)!=data['checks'].get(date,0): fail(400,'历史习惯记录为只读')
        if kind=='library' and data['progress']!=previous['progress']:
            insert(db,'progress',{'date':day(),'title':data['title'],'delta':data['progress']-previous['progress'],'libraryId':identifier,'demo':data['demo']})
            if not data['demo'] and data['progress']>previous['progress']: unlock(db,'library')
        db.execute('UPDATE records SET data=?,version=version+1,updated=? WHERE id=?',(dumps(data),stamp(),identifier)); audit(db,'update:'+kind,identifier)
        result=record(db.execute('SELECT * FROM records WHERE id=?',(identifier,)).fetchone())
    else:
        if kind=='habits' and any(d!=day() for d in data['checks']): fail(400,'新习惯只能记录今天')
        result=insert(db,kind,data,body.get('clientId'))
    if kind=='posts': db.execute("INSERT OR IGNORE INTO post_owners VALUES(?,'owner')",(result['id'],))
    if not data['demo']:
        if kind=='tasks' and data['status']=='done': unlock(db,'task')
        if kind=='habits' and data['checks'].get(day(),0)>=data['target']: unlock(db,'habit')
        if kind=='library' and data['progress']>0 and not identifier: unlock(db,'library')
        if kind in ('health','meals'): unlock(db,'health')
    return result


def remove(db,kind,identifier,version):
    old=db.execute('SELECT * FROM records WHERE id=? AND kind=? AND deleted IS NULL',(identifier,kind)).fetchone()
    if not old or old['userId']!='owner': fail(404,'记录不存在')
    if version!=old['version']: fail(409,'记录已更新，请刷新后重试',current=record(old))
    db.execute('UPDATE records SET deleted=?,updated=?,version=version+1 WHERE id=?',(stamp(),stamp(),identifier)); audit(db,'delete:'+kind,identifier)


def settle_focus(db):
    focus=meta(db,'focus')
    if focus and focus.get('endAt') and focus['endAt']<=millis():
        date=(datetime.fromtimestamp(focus['endAt']/1000,timezone.utc)+timedelta(hours=8)).date().isoformat()
        insert(db,'sessions',{'date':date,'minutes':focus['minutes'],'task':focus['task'] or '自由专注','demo':False})
        set_meta(db,'focus',None)


LINES={'negative':['稍微慢一点，我还没反应过来呢。','隐藏选项也不是这样连点出来的呀。','先去喝口水，再回来好不好？','今天的快进键暂时休息。'],'early':['今天也见到你了，真好。','咖啡还温着，故事慢慢说。','存档已经准备好，今天想走哪条路线？','不用急着通关，日常回也很珍贵。','一小步，也值得记在今天的存档里。'],'close':['你出现的时候，日常就多了一点亮色。','这段剧情，没有你可不行。','今天的好心情，要不要一起存档？','下一次见面，也留在日程里吧。'],'second':['熟悉的开场，但这次知道你会来。','二周目也别快进，好台词值得再看。','咖啡续杯，故事也续一段。','这一次，把喜欢的日常再过一遍。']}


def story_action(db,action):
    s=meta(db,'story',copy.deepcopy(DEFAULT_STORY)); now=millis()
    if action=='finish':
        if s['phase']=='transition': s.update(round=2,points=0)
        elif s['phase']=='epilogue': s.update(round=1,points=0)
        s['phase']='normal'
    elif action=='click':
        if s['phase']!='normal': return s
        s['points']=max(-100,min(100 if s['round']==1 else 200,s['points']+(-50 if now-s['lastClick']<600 else 10)))
        s['lastClick']=now; s['scene']=(s['scene']+1)%3; s['unlocks'].setdefault('hello',now)
        if s['points']==-100: s['unlocks'].setdefault('cold',now)
        if s['round']==1 and s['points']==100: s['phase']='transition'; s['unlocks'].setdefault('second',now)
        if s['round']==2 and s['points']==200: s['phase']='epilogue'; s['unlocks'].setdefault('after',now)
        pool=LINES['negative' if s['points']<0 else 'second' if s['round']==2 else 'close' if s['points']>=60 else 'early']
        choices=[line for line in pool if line not in s['seen']] or [line for line in pool if line!=s['lastLine']]
        s['lastLine']=secrets.choice(choices); s['seen']=(s['seen']+[s['lastLine']])[-3:]
    else: fail(400,'无效操作')
    set_meta(db,'story',s)
    return s


def journal_row(db,r):
    return {**json.loads(r['data']),**author(db,r['userId']),**{k:r[k] for k in ('id','kind','version','created','updated')}}


def image_visible(db,url):
    s=site(db)
    if url in [s['avatarBg'],s['coverImage'],s['blogBackground'],*s['heroImages']]: return True
    if any(json.loads(r['data']).get('avatar')==url for r in db.execute('SELECT data FROM member_profiles')): return True
    if any(p['cover']==url or '('+url+')' in p['content'] for p in public_posts(db)): return True
    for r in db.execute('SELECT data FROM journal'):
        p=json.loads(r['data'])
        if p['status']=='published' and any(i['url']==url for i in p['images']): return True
    return False
