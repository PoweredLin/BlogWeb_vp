// Fixed upstream hosts; credentials stay on the server. Public events are not a full contribution count.
const cache=new Map(),pending=new Map();
export function summarizeEvents(events,provider,username,now=new Date()){
 const end=new Date(now.toISOString().slice(0,10)+'T00:00:00Z'),start=new Date(end.getTime()-364*86400000),counts=new Map();
 for(const e of events){const d=String(e.created_at||'').slice(0,10);if(/^\d{4}-\d{2}-\d{2}$/.test(d))counts.set(d,(counts.get(d)||0)+1);}
 const days=Array.from({length:365},(_,i)=>{const date=new Date(start.getTime()+i*86400000).toISOString().slice(0,10);return {date,count:counts.get(date)||0};});
 return {configured:true,provider,username,profileUrl:`https://${provider==='github'?'github.com':'gitee.com'}/${username}`,days,total:days.reduce((n,d)=>n+d.count,0),updated:now.toISOString(),mode:'public-events',message:'公开动态日历 · 按 UTC 日期统计 API 最近可见的最多 300 条事件，不代表完整年度贡献。空格表示本次未返回事件。'};
}
export async function gitActivity(provider,username){const key=provider+':'+username,cached=cache.get(key);if(cached&&cached.until>Date.now())return cached.value;if(pending.has(key))return pending.get(key);
 const task=(async()=>{try{let events=[];for(let page=1;page<=3;page++){const url=provider==='github'?`https://api.github.com/users/${encodeURIComponent(username)}/events/public?per_page=100&page=${page}`:`https://gitee.com/api/v5/users/${encodeURIComponent(username)}/events/public?per_page=100&page=${page}`;const headers={'User-Agent':'Lin-Notebook','Accept':'application/json'};if(provider==='github'&&process.env.GITHUB_TOKEN)headers.Authorization='Bearer '+process.env.GITHUB_TOKEN;const response=await fetch(url,{headers,redirect:'error',signal:AbortSignal.timeout(8000)});if(!response.ok)throw Error(response.status===404?'没有找到该 Git 账号':response.status===403||response.status===429?'平台请求额度暂时用完':'平台暂时不可用');const data=await response.json();if(!Array.isArray(data))throw Error('平台返回了无法识别的数据');events.push(...data);if(data.length<100)break;}
 const value=summarizeEvents(events,provider,username);if(cache.size>500)cache.delete(cache.keys().next().value);cache.set(key,{until:Date.now()+30*60000,value});return value;
 }catch(e){const value={...(cached?.value||{configured:true,provider,username,days:[]}),stale:!!cached,error:e.name==='TimeoutError'?'连接平台超时，请稍后刷新':e.message};cache.set(key,{until:Date.now()+60000,value});return value;}finally{pending.delete(key);}})();pending.set(key,task);return task;
}
