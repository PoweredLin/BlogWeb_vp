"""Repeatable local demo, isolated from online and normal data directories."""
import argparse
import os
import secrets
from pathlib import Path
from uuid import uuid4
from .main import create_app,ROOT
from .storage import Store,meta,set_meta,stamp,dumps
from .security import credentials
from .validation import DEFAULT_PROFILE,DEFAULT_STORY,CONTRACT,validate_record
from .content import insert
from .automation import validate_config

def seed(store):
    store.initialize();password=None
    with store.transaction() as db:
        if meta(db,'upgradeDemoSeeded'):return
        if not meta(db,'account'):
            password=secrets.token_urlsafe(18);salt,hashed=credentials(password)
            set_meta(db,'account',{'name':'Lin','salt':salt,'hash':hashed})
            set_meta(db,'profile',{**DEFAULT_PROFILE,'name':'Lin'});set_meta(db,'story',DEFAULT_STORY)
        # Content is explicitly marked as demonstration and never replaces existing records.
        from .validation import SITE_DEFAULTS
        set_meta(db,'site',{**SITE_DEFAULTS,**meta(db,'site',{}),'heroMode':'collage'})
        covers=['landscape-fields','landscape-dawn','dimension-sunset','landscape-study','landscape-orbit','landscape-fantasy']
        titles=['给日常留一个存档点','从一段代码开始的午后','下一站，去看看海','写给下一次灵感','我的书桌和未完的故事','把喜欢的东西认真收藏']
        for i,title in enumerate(titles):
            slug='upgrade-demo-'+str(i+1)
            if db.execute("SELECT 1 FROM records WHERE kind='posts' AND json_extract(data,'$.slug')=?",(slug,)).fetchone():continue
            insert(db,'posts',validate_record('posts',{'title':title,'slug':slug,'excerpt':'升级版演示文章，用来体验阅读、封面、列表与个人网站模块。','content':f'# {title}\n\n这是一篇升级版演示文章。正式部署时请使用服务器的原始数据，不能用 demo 数据覆盖。\n\n## 慢慢记录\n\n保留页面的阅读节奏，把复杂配置放在私人空间。\n\n> 故事不需要着急结束。\n\n```python\ndef collect_moments():\n    return ["代码", "旅行", "喜欢的故事"]\n```\n\n## 留给下一页\n\n- 一份清晰的记录\n- 一个可以继续的计划\n- 一点日常里的喜欢','category':'日常手记','tags':'生活','cover':'/assets/'+covers[i]+'.webp','status':'published','publishAt':stamp(),'demo':True}))
        for entry in CONTRACT['demo']:
            if entry['kind']!='posts':insert(db,entry['kind'],validate_record(entry['kind'],entry['data']))
        for kind,data in [('moments',{'title':'升级版 demo','content':'开发书架、文档、自动化结果和页面布局，终于有了自己的位置。','mood':'灵感','status':'published','images':['/assets/landscape-dawn.webp']}),('albums',{'title':'沿途的光','content':'一组用于布局演示的相册。','mood':'晴','status':'published','images':['/assets/landscape-fields.webp','/assets/landscape-fantasy.webp']})]:
            db.execute('INSERT INTO journal(id,kind,userId,data,created,updated) VALUES(?,?,\'owner\',?,?,?)',(str(uuid4()),kind,dumps(data),stamp(),stamp()))
        db.execute('INSERT INTO private_documents(id,title,category,content,created,updated) VALUES(?,?,?,?,?,?)',(str(uuid4()),'升级版体验路线','使用说明','# 欢迎来到升级版 demo\n\n1. 管理 → 页面布局，调整首页与房间模块。\n2. 管理 → 开发书架，查阅文档。\n3. 管理 → 自动化，运行季度新番并预览。\n4. AI 接入，给本地 AI 创建最小权限 Token。\n\n```mermaid\nflowchart LR\n A[本地 AI / 云端轻量采集] --> B[私人预览]\n B --> C{人工确认}\n C --> D[私有文档]\n C --> E[兴趣收藏]\n C --> F[邮箱]\n```',stamp(),stamp()))
        for template,name,config in [('seasonal-anime','本季度新番 · 手动预览',{'saveLibrary':True,'limit':8}),('weekly-review','我的空间周报',{}),('local-digest','本地 AI 资料收件箱',{})]:
            if not db.execute('SELECT 1 FROM automation_flows WHERE template=?',(template,)).fetchone():db.execute('INSERT INTO automation_flows VALUES(?,?,?,?,0,1,?,?)',(str(uuid4()),name,template,dumps(validate_config(template,config)),stamp(),stamp()))
        from .page_layout import DEFAULT
        layout={**DEFAULT,'version':1,'home':[{'id':'profile','enabled':True},{'id':'articles','enabled':True},{'id':'moments','enabled':True},{'id':'albums','enabled':True}]}
        set_meta(db,'pageLayout',layout);set_meta(db,'upgradeDemoSeeded',True)
    if password:print('Demo username: admin\nDemo password: '+password,flush=True)
    else:print('Existing demo account retained; password unchanged.',flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=4321);p.add_argument('--data-dir',default=str(ROOT/'data/demo-v10'));a=p.parse_args()
    directory=Path(a.data_dir).resolve()
    expected=(ROOT/'data'/'demo-v10').resolve()
    if directory!=expected:p.error('Demo data is fixed to data/demo-v10; use the production app for other data directories')
    os.environ['APP_ENV']='development';os.environ['COOKIE_SECURE']='false';os.environ['HOST']='127.0.0.1'
    store=Store(directory);seed(store)
    print('Local demo: http://127.0.0.1:'+str(a.port)+'\nData: '+str(directory),flush=True)
    import uvicorn
    uvicorn.run(create_app(directory,production=False,site_url=f'http://127.0.0.1:{a.port}'),host='127.0.0.1',port=a.port,limit_concurrency=32)

if __name__=='__main__':main()
