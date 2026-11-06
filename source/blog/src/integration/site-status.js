import {computed, ref} from 'vue';

const status=ref(null),state=ref('loading'),clock=ref(Date.now());
let users=0,timer=null,lastCheck=0,pending=null;
async function check(){
 if(pending||Date.now()-lastCheck<60000)return;
 lastCheck=Date.now();
 pending=(async()=>{const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),6000);
  try{const response=await fetch('/api/public/status',{signal:controller.signal,credentials:'omit',cache:'no-store'});if(!response.ok)throw Error();status.value=await response.json();state.value=status.value.ok?'online':'unavailable';}
  catch{state.value='unavailable';}finally{clearTimeout(timeout);pending=null;}
 })();await pending;
}
function tick(){clock.value=Date.now();if(!document.hidden)check();}
function visibility(){if(!document.hidden)tick();}
export function retainStatus(){if(++users===1){tick();timer=setInterval(tick,60000);document.addEventListener('visibilitychange',visibility);}return()=>{if(--users===0){clearInterval(timer);document.removeEventListener('visibilitychange',visibility);}};}
export const serviceLabel=computed(()=>({loading:'正在检查服务',online:'服务正常',unavailable:'暂时无法确认服务状态'})[state.value]);
export const serviceState=state;
export const siteSince=computed(()=>status.value?.siteStartedAt||'');
export const runtimeLabel=computed(()=>{
 const start=Date.parse(siteSince.value);if(!Number.isFinite(start))return '建站日期待设置';
 const minutes=Math.max(0,Math.floor((clock.value-start)/60000));
 return `${Math.floor(minutes/1440)} 天 ${Math.floor(minutes%1440/60)} 小时 ${minutes%60} 分钟`;
});
