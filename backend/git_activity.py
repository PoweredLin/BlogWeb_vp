"""Persistent stale-while-revalidate activity. The request never waits for Git hosts."""
import asyncio
import json
import os
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import httpx
from .storage import dumps
from .security import millis


class GitActivity:
    ttl=30*60*1000
    def __init__(self,store,transport=None):
        self.store=store; self.transport=transport; self.tasks=set()

    def read(self,provider,username):
        if not username: return {'configured':False,'days':[],'message':'在个人设置中填写 Git 用户名，点亮你的代码日历。'}
        if provider not in ('github','gitee') or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,38}',username): raise ValueError('Invalid Git identity')
        key=provider+':'+username.lower(); now=millis()
        with self.store.transaction() as db:
            db.execute('INSERT OR IGNORE INTO git_cache(key,data) VALUES(?,?)',(key,'{}'))
            row=dict(db.execute('SELECT * FROM git_cache WHERE key=?',(key,)).fetchone())
            refresh=row['next_attempt']<=now and row['lease_until']<=now
            if refresh: db.execute('UPDATE git_cache SET lease_until=? WHERE key=?',(now+30000,key))
        if refresh:
            task=asyncio.create_task(self.refresh(key,provider,username,row))
            self.tasks.add(task); task.add_done_callback(self.tasks.discard)
        payload=json.loads(row['data'])
        return {**self.empty(provider,username),**payload,'cached':True,'stale':row['updated']+self.ttl<=now,'refreshing':refresh or row['lease_until']>now,'updatedAt':datetime.fromtimestamp(row['updated']/1000,timezone.utc).isoformat() if row['updated'] else None,'message':row['error'] or ('公开动态日历 · 按 UTC 统计最近最多 100 条事件，不代表完整年度贡献。' if row['updated'] else '正在后台同步公开动态，稍后重新查看即可。')}

    def empty(self,provider,username):
        today=datetime.now(timezone.utc).date()
        return {'configured':True,'provider':provider,'username':username,'profileUrl':f'https://{ "github.com" if provider=="github" else "gitee.com"}/{username}','mode':'public-events','total':0,'days':[{'date':(today-timedelta(days=i)).isoformat(),'count':0} for i in range(364,-1,-1)]}

    async def refresh(self,key,provider,username,old):
        next_attempt=millis()+self.ttl; error=''; data=old['data']; etag=old['etag']; updated=old['updated']
        try:
            headers={'User-Agent':'LinNotebook/9','Accept':'application/json'}
            if etag: headers['If-None-Match']=etag
            if provider=='github' and os.getenv('GITHUB_TOKEN'): headers['Authorization']='Bearer '+os.environ['GITHUB_TOKEN']
            url=f'https://api.github.com/users/{username}/events/public' if provider=='github' else f'https://gitee.com/api/v5/users/{username}/events/public'
            # One conditional page per interval. No pagination fan-out and no redirects.
            async with asyncio.timeout(6):
                async with httpx.AsyncClient(timeout=5,follow_redirects=False,transport=self.transport,trust_env=False) as client:
                    async with client.stream('GET',url,params={'per_page':100},headers=headers) as response:
                        if response.status_code==304: updated=millis()
                        elif response.status_code in (403,429):
                            next_attempt=max(next_attempt,self.retry_at(response))
                            error='平台暂时限制访问，已保留上次结果并延后同步。'
                        else:
                            response.raise_for_status()
                            raw=bytearray()
                            async for chunk in response.aiter_bytes():
                                raw.extend(chunk)
                                if len(raw)>2*1024*1024: raise ValueError('Response too large')
                            events=json.loads(raw)
                            if not isinstance(events,list): raise ValueError('Invalid response')
                            result=self.empty(provider,username); counts={}
                            for event in events:
                                if not isinstance(event,dict): continue
                                date=str(event.get('created_at',''))[:10]
                                counts[date]=counts.get(date,0)+1
                            for day in result['days']: day['count']=counts.get(day['date'],0)
                            result['total']=sum(d['count'] for d in result['days'])
                            data=dumps(result); etag=response.headers.get('etag'); updated=millis()
        except asyncio.CancelledError:
            raise
        except (httpx.HTTPError,TimeoutError,ValueError,TypeError):
            error='暂时无法同步，已保留上次结果，稍后自动重试。'
            next_attempt=millis()+15*60*1000
        finally:
            with self.store.transaction() as db:
                db.execute('UPDATE git_cache SET data=?,etag=?,updated=?,next_attempt=?,lease_until=0,error=? WHERE key=?',(data,etag,updated,next_attempt,error,key))

    def retry_at(self,response):
        now=millis(); retry=now+3600000
        try: retry=max(retry,int(response.headers.get('x-ratelimit-reset','0'))*1000)
        except ValueError: pass
        value=response.headers.get('retry-after','')
        try: retry=max(retry,now+int(value)*1000)
        except ValueError:
            try: retry=max(retry,int(parsedate_to_datetime(value).timestamp()*1000))
            except (ValueError,TypeError,OverflowError): pass
        return min(retry,now+24*3600000)

    async def close(self):
        for task in self.tasks: task.cancel()
        await asyncio.gather(*self.tasks,return_exceptions=True)
