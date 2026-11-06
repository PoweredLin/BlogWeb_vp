<script setup>
import {ref,computed,onMounted,onBeforeUnmount,onActivated} from 'vue';import {request} from './service';import {useRouter} from 'vue-router';import LinIcon from './LinIcon.vue';import Waves from '@/components/WelcomeComps/waves.vue';import TypeWriter from '@/components/TypeWriter/type-writer.vue';import LinFrameIntro from './LinFrameIntro.vue';
const router=useRouter();
const layout=ref({introEnabled:true,introReplay:"session",introPhotoMode:'auto',introPhotos:[]});
const site=ref({}),posts=ref([]),me=ref(null),index=ref(0),now=ref(new Date()),busy=ref(false),poster=ref(null),scene=ref(localStorage.getItem('lin-local-scenery')||''),showIntro=ref(false),introComplete=ref(false),heroReady=ref(false);
let rotator,clock;
const reduced=typeof matchMedia==='function'&&matchMedia('(prefers-reduced-motion: reduce)').matches;
const mode=computed(()=>'poster');
const heroList=computed(()=>{const list=Array.isArray(site.value.heroImages)?site.value.heroImages.filter(Boolean):[];return [...new Set(list.length?list:[site.value.cover||'landscape-fields'])];});
const introPhotos=computed(()=>layout.value.introPhotoMode==='custom'?layout.value.introPhotos:[...new Set([...heroList.value.map(imageUrl),...posts.value.map(post=>post.cover).filter(Boolean)])].slice(0,8));
const siteName=computed(()=>site.value.title||'林间笔记');
const title=computed(()=>site.value.heroTitle||site.value.title||'林间笔记');
const tail=computed(()=>site.value.heroTail==='的随记'?'':site.value.heroTail||'');
const imageUrl=v=>v.startsWith('/')?v:'/assets/'+v+'.webp';
const label=computed(()=>site.value.heroLabel||'A PLACE TO SLOW DOWN');
const cue=computed(()=>site.value.scrollCue||'往下翻翻');
const veil=computed(()=>(Math.min(80,Math.max(0,Number(site.value.heroOverlay)||0)))/100);
const sayings=computed(()=>[...new Set([site.value.heroIntro,site.value.subtitle].map(x=>String(x||'').trim()).filter(Boolean))].slice(0,2));
const isAdmin=computed(()=>me.value?.role==='admin');
const avatar=computed(()=>me.value?.avatar||site.value.avatar||'/favicon.svg');
const greeting=()=>now.value.getHours()<11?'早上好，今天也有新故事。':now.value.getHours()<18?'午后好，让思绪慢一点。':'晚上好，把今天收藏起来。';
function scenery(value){scene.value=value;localStorage.setItem('lin-local-scenery',value);}
async function random(){busy.value=true;setTimeout(()=>{busy.value=false;if(posts.value.length)router.push('/blog/'+posts.value[Math.floor(Math.random()*posts.value.length)].slug);},300);}
function onScroll(){if(!poster.value)return;const h=poster.value.offsetHeight||1;poster.value.style.setProperty('--poster-shift',Math.min(1,scrollY/h)*30+'px');}
onMounted(async()=>{
 const [initial,st]=await Promise.all([request('/api/public/bootstrap').catch(()=>({site:{},featuredPosts:[],layout:{introEnabled:false,introReplay:'session'}})),request('/api/status').catch(()=>({}))]);
 const s=initial.site,p=initial.featuredPosts,l=initial.layout||{introEnabled:false,introReplay:'session'};
 site.value=s||{};posts.value=p||[];me.value=st?.user||null;layout.value=l;showIntro.value=l.introEnabled!==false&&s?.motion!==false;heroReady.value=true;
 clock=setInterval(()=>now.value=new Date(),60000);
 if(!reduced&&s?.motion!==false&&heroList.value.length>1)rotator=setInterval(()=>{if(!document.hidden)index.value=(index.value+1)%heroList.value.length;},Math.min(60,Math.max(3,Number(s?.heroInterval)||8))*1000);
 if(!reduced&&s?.motion!==false)addEventListener('scroll',onScroll,{passive:true});
});
// The home page is kept alive, so coming back to it replays the intro and re-runs the poster entrance.
const heroCycle=ref(0),titleChars=computed(()=>[...title.value]);
const fireflies=Array.from({length:16},(_,i)=>({left:(i*37%97)+'%',top:(20+i*53%70)+'%','--d':(i*.7%6)+'s','--t':(7+i%5*1.6)+'s','--x':((i%2?1:-1)*(20+i*13%40))+'px'}));
let firstActivation=true;
onActivated(()=>{if(firstActivation){firstActivation=false;return;}if(!heroReady.value||layout.value.introEnabled===false||site.value.motion===false)return;introComplete.value=false;heroCycle.value++;showIntro.value=true;});
onBeforeUnmount(()=>{clearInterval(rotator);clearInterval(clock);removeEventListener('scroll',onScroll);});
</script>
<template>
<section v-if="mode==='poster'" ref="poster" class="lin-poster" :class="{'is-waiting':!heroReady||(showIntro&&!introComplete)}" data-poster :style="{'--poster-veil':veil}">
 <div class="poster-stack" aria-hidden="true"><img v-for="(img,i) in heroList" :key="img" :src="imageUrl(img)" :class="{on:i===index}" :fetchpriority="i===0?'high':'low'" alt=""></div>
 <div class="poster-veil" aria-hidden="true"></div>
 <div class="poster-fireflies" aria-hidden="true"><i v-for="(f,i) in fireflies" :key="i" :style="f"/></div>
 <div class="poster-body" :key="heroCycle">
  <span class="poster-label"><i/>{{label}}</span>
  <h1 class="poster-title" :aria-label="title+(tail||'')"><span v-for="(ch,i) in titleChars" :key="i" class="ch" :style="{'--i':i}" aria-hidden="true">{{ch}}</span><em v-if="tail" aria-hidden="true">{{tail}}</em></h1>
  <div class="poster-say"><span v-if="reduced || site.motion===false">{{sayings[0]}}</span><TypeWriter v-else-if="sayings.length && site.motion!==false" :typeList="sayings" size="1em"/></div>
  <div class="poster-actions"><a href="#latest" class="lin-primary">翻开随手记 <LinIcon name="arrow"/></a><button class="lin-random" @click="random" :disabled="busy||!posts.length"><LinIcon name="spark" :class="{spinning:busy}"/>随便逛逛</button></div>
 </div>
 <div v-if="heroList.length>1" class="poster-dots" role="tablist" aria-label="换一张海报"><button v-for="(img,i) in heroList" :key="img" role="tab" :aria-selected="i===index" :aria-label="'第 '+(i+1)+' 张海报'" :class="{on:i===index}" @click="index=i"/></div>
 <a href="#latest" class="poster-cue" :aria-label="cue"><span>{{cue}}</span><b>⌄</b></a>
 <Waves height="5rem"/>
</section>
<section v-else class="lin-hero"><div class="lin-hero-copy"><span class="lin-eyebrow"><i/> A SMALL CORNER OF MY WORLD</span><p class="lin-greeting">{{greeting()}}</p><h1>把日子写成<br><em>喜欢的模样<span class="hero-spark">✳</span></em></h1><p class="lin-hero-desc">{{site.subtitle}}</p><div class="hero-actions"><a href="#latest" class="lin-primary">翻开随手记 <LinIcon name="arrow"/></a><button class="lin-random" @click="random" :disabled="busy||!posts.length"><LinIcon name="spark" :class="{spinning:busy}"/>随便逛逛</button></div><div class="lin-coordinate"><span>日常观察员 / 偶尔写代码</span><span>{{now.toLocaleDateString('zh-CN',{month:'long',day:'numeric'})}} · 随时更新</span></div></div><div class="lin-hero-art"><div class="orbit-text">COLLECT MOMENTS · NOT THINGS ·</div><a href="/albums" class="polaroid main-photo"><img :src="'/assets/'+(scene||site.cover||'landscape-fields')+'.webp'" alt="收藏沿途的风景"/><span>今天的天空，也很好看。 <b>01 / 日常取景</b></span></a><a href="/albums" class="polaroid small-photo"><img src="/assets/landscape-study.webp" alt="一盏书桌的灯"/><span>留一点时间，给自己。</span></a><div class="lin-sticker"><LinIcon name="heart" :size="18"/> 热爱可抵岁月漫长</div><div class="scenery-switch"><button v-for="(s,i) in ['landscape-fields','landscape-dawn','landscape-fantasy']" :key="s" :class="{chosen:scene===s}" :aria-label="'换个景色 '+(i+1)+'（仅此设备）'" @click="scenery(s)">{{String(i+1).padStart(2,'0')}}</button></div><span class="scribble">keep a little wonder ↗</span></div></section>
<div v-if="!heroReady" class="intro-loading" aria-label="正在加载首页"/>
<LinFrameIntro v-if="showIntro" :title="layout.introTitle||siteName" :photos="introPhotos" replay="always" @reveal="introComplete=true" @done="showIntro=false;introComplete=true"/>
<div v-if="site.showTicker!==false" class="lin-ticker"><div><span v-for="n in 4" :key="n">CODE & COFFEE <b>✦</b> 番剧放映室 <b>✦</b> 游戏存档点 <b>✦</b> SMALL JOYS <b>✦</b> 后日谈 <b>✦</b></span></div></div>
<section id="latest" class="lin-section-heading"><div><span class="lin-eyebrow">THE LATEST PAGES</span><h2>最近写下的 <i>Notes.</i></h2></div><a href="/category">按分类翻阅 <LinIcon name="arrow" :size="17"/></a></section>
</template>
<style lang="scss" scoped>
.intro-loading{position:fixed;inset:0;z-index:9998;background:#151918}
/* Title rises in character by character with a little overshoot. */
.poster-title .ch{display:inline-block;white-space:pre;animation:ch-rise .9s cubic-bezier(.2,1.4,.4,1) calc(.25s + var(--i)*.07s) both}
.lin-poster.is-waiting .poster-title .ch{animation-play-state:paused}
@keyframes ch-rise{from{opacity:0;transform:translateY(.7em) rotate(10deg) scale(.8);filter:blur(8px)}to{opacity:1;transform:none;filter:none}}
.poster-title:hover .ch{animation:ch-wave .6s ease calc(var(--i)*.05s)}
@keyframes ch-wave{50%{transform:translateY(-.12em);color:#f1bf5b}}
/* Fireflies drifting over the poster — the "林间" part of the name. */
.poster-fireflies{position:absolute;inset:0;z-index:3;pointer-events:none;overflow:hidden}
.poster-fireflies i{position:absolute;width:5px;height:5px;border-radius:50%;background:#ffe39a;box-shadow:0 0 8px 2px #f1bf5baa,0 0 18px 4px #e6a93a55;opacity:0;animation:firefly var(--t) ease-in-out var(--d) infinite}
@keyframes firefly{0%{opacity:0;transform:translate(0,0)}20%{opacity:.9}50%{opacity:.35;transform:translate(var(--x),-40px)}80%{opacity:.85}100%{opacity:0;transform:translate(calc(var(--x)*-.5),-90px)}}
.lin-poster{position:relative;width:100%;height:calc(100vh - 14px);min-height:620px;max-height:1000px;overflow:hidden;display:flex;align-items:center;justify-content:center;background:#1c2422;color:#fff}
.poster-stack{position:absolute;inset:0;z-index:1;transform:translate3d(0,var(--poster-shift,0),0);will-change:transform}
.poster-stack img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:center 52%;opacity:0;transform:scale(1.04);transition:opacity 1.1s ease}
.poster-stack img.on{opacity:1;animation:poster-drift 16s ease-in-out infinite alternate}
@keyframes poster-drift{from{transform:scale(1.02)}to{transform:scale(1.13)}}
.poster-veil{position:absolute;inset:0;z-index:2}
.poster-veil::before{content:"";position:absolute;inset:0;background:linear-gradient(180deg,#0b141b9e,transparent 34%,transparent 58%,#0b141bd6)}
.poster-veil::after{content:"";position:absolute;inset:0;background:#0a1219;opacity:var(--poster-veil,.3)}
.poster-body{position:relative;z-index:5;width:min(940px,88vw);text-align:center;padding:96px 0 0;text-shadow:0 2px 30px #0012206b;animation:poster-in 1.1s cubic-bezier(.22,.68,.35,1) both}
.poster-label{display:inline-flex;align-items:center;gap:12px;font-size:10px;font-weight:600;letter-spacing:5px;text-transform:uppercase;opacity:.82}
.poster-label i{width:26px;height:1px;background:currentColor;opacity:.55}
.poster-title{margin:24px 0 0;font-size:clamp(40px,7.2vw,88px);font-weight:600;letter-spacing:-1px;line-height:1.06;animation:poster-in 1.1s .12s cubic-bezier(.22,.68,.35,1) both}
.poster-title em{display:block;margin-top:10px;font-style:normal;font-size:.44em;font-weight:400;letter-spacing:14px;opacity:.9}
.poster-say{margin:22px auto 0;max-width:640px;font-size:15px;letter-spacing:2px;line-height:1.9;opacity:.94;min-height:30px;animation:poster-in 1.1s .24s cubic-bezier(.22,.68,.35,1) both}
.poster-actions{display:flex;align-items:center;justify-content:center;gap:16px;margin-top:32px;animation:poster-in 1.1s .36s cubic-bezier(.22,.68,.35,1) both}
.poster-actions .lin-random{color:#fff;padding:13px 18px;border:1px solid #ffffff5e;border-radius:8px;background:#0d172036}
.poster-dots{position:absolute;left:50%;bottom:95px;z-index:6;display:flex;gap:9px;transform:translateX(-50%)}
.poster-dots button{width:26px;height:3px;padding:0;border:0;border-radius:2px;background:#ffffff59;cursor:pointer;transition:background .3s,width .3s}
.poster-dots button.on{width:40px;background:#fff}
.poster-strip{position:absolute;left:0;right:0;bottom:64px;z-index:6;display:flex;align-items:center;justify-content:space-between;gap:14px;padding:0 clamp(20px,5vw,64px);font-size:11px;letter-spacing:1px;color:#ffffffd9}
.strip-who{display:inline-flex;align-items:center;gap:9px}
.strip-who img{width:26px;height:26px;border-radius:50%;object-fit:cover;border:1px solid #ffffff73;background:#ffffff1f}
.strip-who b{font-weight:500}
.strip-who small{font-size:9px;letter-spacing:2px;padding:2px 7px;border:1px solid #ffffff59;border-radius:20px;opacity:.8}
.strip-links{display:inline-flex;align-items:center;gap:14px;flex-wrap:wrap;justify-content:flex-end}
.strip-links a{color:#fff;border-bottom:1px solid #ffffff6b;padding-bottom:2px}
.strip-links a:hover{border-color:#fff}
.poster-cue{position:absolute;left:50%;bottom:26px;z-index:6;display:flex;flex-direction:column;align-items:center;gap:3px;font-size:10px;letter-spacing:3px;color:#ffffffc7;transform:translateX(-50%)}
.poster-cue b{font-size:15px;animation:poster-bounce 2s infinite}
/* Hold the poster entrance behind the intro so the reveal lands right as the intro dissolves. */
.lin-poster.is-waiting .poster-body,.lin-poster.is-waiting .poster-body>*{animation-play-state:paused}
.lin-poster.is-waiting .poster-stack{filter:blur(6px) brightness(.7)}
.lin-poster.is-waiting .poster-stack img.on{animation-play-state:paused}
.lin-poster:not(.is-waiting) .poster-stack{animation:poster-settle 1.6s cubic-bezier(.2,.7,.2,1) both}
@keyframes poster-settle{from{filter:blur(6px) brightness(.7)}to{filter:none}}
@keyframes poster-in{from{opacity:0;transform:translateY(26px);filter:blur(4px)}to{opacity:1;transform:none;filter:none}}
@keyframes poster-bounce{0%,100%{transform:translateY(0);opacity:.45}50%{transform:translateY(6px);opacity:1}}
@media(prefers-reduced-motion:reduce){.lin-poster .poster-stack,.lin-poster .poster-body,.lin-poster .poster-body>*,.lin-poster .poster-title .ch{animation:none!important;filter:none!important}.poster-fireflies{display:none}}
@media(max-width:800px){
 .lin-poster{height:calc(100vh - 68px);min-height:540px}
 .poster-body{padding-top:70px}
 .poster-strip{bottom:56px;flex-direction:column;align-items:flex-start;gap:8px;font-size:10px}
 .poster-dots{bottom:150px}
 .poster-cue{bottom:14px}
}
</style>
