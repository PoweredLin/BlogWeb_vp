import {icon as original} from './icons.js';
const extra={heart:'<path d="M20 9a5 5 0 0 0-8-4 5 5 0 0 0-8 4c0 6 8 11 8 11s8-5 8-11Z"/>',lock:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/>',globe:'<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/>',focus:'<circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2M9 1h6"/>'};
export const icon=(name,size=20)=>extra[name]?`<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${extra[name]}</svg>`:original(({sleep:'moon',writing:'edit',review:'review',sparkles:'spark',plus:'plus',logout:'arrow',game:'library',coffee:'focus'})[name]||name,size);
export const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const today=(offset=0)=>new Date(Date.now()+offset*86400000).toLocaleDateString('en-CA',{timeZone:'Asia/Shanghai'});
export const duration=n=>`${Math.floor((n||0)/60)} 小时 ${(n||0)%60} 分钟`;
export const number=n=>Number(n||0).toLocaleString('zh-CN');
export const label=(text,sub='')=>`<div class="section-label">${text}${sub?`<span>${sub}</span>`:''}</div>`;
export const button=(text,action,cls='',attrs='')=>`<button type="button" class="button ${cls}" data-action="${action}" ${attrs}>${text}</button>`;
export const empty=(title='这一页，等你来写',sub='从第一条记录开始，慢慢收集自己的日常。')=>`<div class="empty">${icon('spark',28)}<h3>${title}</h3><p>${sub}</p></div>`;
export const img=(name,cls='',alt='')=>`<img class="${cls}" src="/assets/${name}.webp" alt="${esc(alt)}" loading="lazy">`;
export const tag=t=>`<span class="tag">${esc(t)}</span>`;
export const chips=s=>(s||'').split(/[,，]/).filter(Boolean).map(tag).join('');
export const field=(name,title,value='',type='text',extra='')=>`<label class="field">${title}<input name="${name}" type="${type}" value="${esc(value)}" ${extra}></label>`;
export const area=(name,title,value='',extra='')=>`<label class="field">${title}<textarea name="${name}" ${extra}>${esc(value)}</textarea></label>`;
export const select=(name,title,choices,value)=>`<label class="field">${title}<select name="${name}">${choices.map(x=>{const [v,t]=Array.isArray(x)?x:[x,x];return `<option value="${esc(v)}" ${v===value?'selected':''}>${esc(t)}</option>`;}).join('')}</select></label>`;
let previousFocus;
export function modal(title,body,wide=false){previousFocus=document.activeElement;const el=document.querySelector('#modal');el.className=wide?'wide':'';el.innerHTML=`<header><div><span class="eyebrow">A LITTLE MOMENT</span><h2>${title}</h2></div><button type="button" class="icon-button" data-action="close" aria-label="关闭弹窗">${icon('close')}</button></header>${body}`;if(!el.open)el.showModal();positionToolDialog();el.addEventListener('close',()=>previousFocus?.isConnected&&previousFocus.focus(),{once:true});}
export function close(){document.querySelector('#modal').close();}
let timer;export function toast(text){const el=document.querySelector('#toast');el.textContent=text;el.classList.add('visible');clearTimeout(timer);timer=setTimeout(()=>el.classList.remove('visible'),4500);}
export async function api(url,options={}){const response=await fetch(url,{headers:{'Content-Type':'application/json'},...options,body:options.body!==undefined?JSON.stringify(options.body):undefined});const data=await response.json();if(!response.ok){const err=Object.assign(Error(data.error||'请求未完成'),{status:response.status,...data});throw err;}return data;}
export const saveRequest=(kind,data)=>api('/api/private/records/'+kind+(data.id?'/'+data.id:''),{method:data.id?'PUT':'POST',body:data});
export function download(name,value,type='application/json'){const url=URL.createObjectURL(new Blob([value],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
export const formFooter=(deleteButton='')=>`<div class="form-footer">${deleteButton}<span></span><button type="button" class="button" data-action="close">取消</button><button class="button primary" type="submit">保存记录 ${icon('check',16)}</button></div><p class="form-error" role="alert"></p>`;

function positionToolDialog(){const el=document.querySelector('#modal');if(!el?.open||window.parent===window)return;try{const box=window.frameElement.getBoundingClientRect(),h=window.parent.innerHeight;el.style.top=Math.max(16,-box.top+Math.max(90,h*.12))+'px';el.style.bottom='auto';el.style.margin='0 auto';el.style.maxHeight=Math.max(260,h*.76)+'px';}catch{}}
if(window.parent!==window){try{window.parent.addEventListener('scroll',positionToolDialog,{passive:true});window.parent.addEventListener('resize',positionToolDialog);addEventListener('pagehide',()=>{window.parent.removeEventListener('scroll',positionToolDialog);window.parent.removeEventListener('resize',positionToolDialog);});}catch{}}
