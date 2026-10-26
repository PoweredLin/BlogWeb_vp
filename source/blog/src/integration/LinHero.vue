<script setup>
import {ref,computed,onMounted,onBeforeUnmount} from 'vue';import {request} from './service';import {useRouter} from 'vue-router';import LinIcon from './LinIcon.vue';import Waves from '@/components/WelcomeComps/waves.vue';import TypeWriter from '@/components/TypeWriter/type-writer.vue';
const router=useRouter();
const site=ref({}),posts=ref([]),me=ref(null),index=ref(0),now=ref(new Date()),busy=ref(false),poster=ref(null),scene=ref(localStorage.getItem('lin-local-scenery')||'');
let rotator,clock;
const reduced=typeof matchMedia==='function'&&matchMedia('(prefers-reduced-motion: reduce)').matches;
const mode=computed(()=>site.value.heroMode==='collage'?'collage':'poster');
const heroList=computed(()=>{const list=Array.isArray(site.value.heroImages)?site.value.heroImages.filter(Boolean):[];return [...new Set(list.length?list:[site.value.cover||'landscape-fields'])];});
const title=computed(()=>site.value.heroTitle||site.value.title||'Lin 的随手记');
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
 const [s,p,st]=await Promise.all([request('/api/site'),request('/api/public').then(x=>x.posts).catch(()=>[]),request('/api/status').catch(()=>({}))]);
 site.value=s||{};posts.value=p||[];me.value=st?.user||null;
 clock=setInterval(()=>now.value=new Date(),60000);
 if(!reduced&&s?.motion!==false&&heroList.value.length>1)rotator=setInterval(()=>{if(!document.hidden)index.value=(index.value+1)%heroList.value.length;},Math.min(60,Math.max(3,Number(s?.heroInterval)||8))*1000);
 if(!reduced&&s?.motion!==false)addEventListener('scroll',onScroll,{passive:true});
});
onBeforeUnmount(()=>{clearInterval(rotator);clearInterval(clock);removeEventListener('scroll',onScroll);});
</script>
<template>
<section v-if="mode==='poster'" ref="poster" class="lin-poster" data-poster :style="{'--poster-veil':veil}">
 <div class="poster-stack" aria-hidden="true"><img v-for="(img,i) in heroList" :key="img" :src="imageUrl(img)" :class="{on:i===index}" :fetchpriority="i===0?'high':'low'" alt=""></div>
 <div class="poster-veil" aria-hidden="true"></div>
 <div class="poster-body">
  <span class="poster-label"><i/>{{label}}</span>
  <h1 class="poster-title">{{title}}<em v-if="tail">{{tail}}</em></h1>
  <div class="poster-say"><span v-if="reduced || site.motion===false">{{sayings[0]}}</span><TypeWriter v-else-if="sayings.length && site.motion!==false" :typeList="sayings" size="1em"/></div>
  <div class="poster-actions"><a href="#latest" class="lin-primary">翻开随手记 <LinIcon name="arrow"/></a><button class="lin-random" @click="random" :disabled="busy||!posts.length"><LinIcon name="spark" :class="{spinning:busy}"/>随便逛逛</button></div>
 </div>
 <div v-if="heroList.length>1" class="poster-dots" role="tablist" aria-label="换一张海报"><button v-for="(img,i) in heroList" :key="img" role="tab" :aria-selected="i===index" :aria-label="'第 '+(i+1)+' 张海报'" :class="{on:i===index}" @click="index=i"/></div>
 <a href="#latest" class="poster-cue" :aria-label="cue"><span>{{cue}}</span><b>⌄</b></a>
 <Waves height="5rem"/>
</section>
<section v-else class="lin-hero"><div class="lin-hero-copy"><span class="lin-eyebrow"><i/> A SMALL CORNER OF MY WORLD</span><p class="lin-greeting">{{greeting()}}</p><h1>把日子写成<br><em>喜欢的模样<span class="hero-spark">✳</span></em></h1><p class="lin-hero-desc">{{site.subtitle}}</p><div class="hero-actions"><a href="#latest" class="lin-primary">翻开随手记 <LinIcon name="arrow"/></a><button class="lin-random" @click="random" :disabled="busy||!posts.length"><LinIcon name="spark" :class="{spinning:busy}"/>随便逛逛</button></div><div class="lin-coordinate"><span>日常观察员 / 偶尔写代码</span><span>{{now.toLocaleDateString('zh-CN',{month:'long',day:'numeric'})}} · 随时更新</span></div></div><div class="lin-hero-art"><div class="orbit-text">COLLECT MOMENTS · NOT THINGS ·</div><a href="/albums" class="polaroid main-photo"><img :src="'/assets/'+(scene||site.cover||'landscape-fields')+'.webp'" alt="收藏沿途的风景"/><span>今天的天空，也很好看。 <b>01 / 日常取景</b></span></a><a href="/albums" class="polaroid small-photo"><img src="/assets/landscape-study.webp" alt="一盏书桌的灯"/><span>留一点时间，给自己。</span></a><div class="lin-sticker"><LinIcon name="heart" :size="18"/> 热爱可抵岁月漫长</div><div class="scenery-switch"><button v-for="(s,i) in ['landscape-fields','landscape-dawn','landscape-fantasy']" :key="s" :class="{chosen:scene===s}" :aria-label="'换个景色 '+(i+1)+'（仅此设备）'" @click="scenery(s)">{{String(i+1).padStart(2,'0')}}</button></div><span class="scribble">keep a little wonder ↗</span></div></section>
<div v-if="site.showTicker!==false" class="lin-ticker"><div><span v-for="n in 4" :key="n">CODE & COFFEE <b>✦</b> 番剧放映室 <b>✦</b> 游戏存档点 <b>✦</b> SMALL JOYS <b>✦</b> 后日谈 <b>✦</b></span></div></div>
<section id="latest" class="lin-section-heading"><div><span class="lin-eyebrow">THE LATEST PAGES</span><h2>最近写下的 <i>Notes.</i></h2></div><a href="/category">按分类翻阅 <LinIcon name="arrow" :size="17"/></a></section>
</template>
<style lang="scss" scoped>
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
@keyframes poster-in{from{opacity:0;transform:translateY(26px)}to{opacity:1;transform:none}}
@keyframes poster-bounce{0%,100%{transform:translateY(0);opacity:.45}50%{transform:translateY(6px);opacity:1}}
@media(max-width:800px){
 .lin-poster{height:calc(100vh - 68px);min-height:540px}
 .poster-body{padding-top:70px}
 .poster-strip{bottom:56px;flex-direction:column;align-items:flex-start;gap:8px;font-size:10px}
 .poster-dots{bottom:150px}
 .poster-cue{bottom:14px}
}
</style>
