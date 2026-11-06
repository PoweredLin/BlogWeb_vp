<script setup>
import {onBeforeUnmount,onMounted,ref} from 'vue';

const props=defineProps({title:{type:String,required:true},photos:{type:Array,default:()=>[]},replay:{type:String,default:'session'}});
// `reveal` fires when the exit burst starts so the page underneath can begin its entrance; `done` keeps its old meaning.
const emit=defineEmits(['done','reveal']);
const canvas=ref(null),finished=ref(false),stage=ref('wait');
let frame=0,resizeHandler,keyHandler,disposed=false,revealed=false;
const timers=new Set();
const reducedMotion=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
function later(callback,delay){const id=window.setTimeout(()=>{timers.delete(id);if(!disposed)callback();},delay);timers.add(id);return id;}
function reveal(){if(!revealed){revealed=true;emit('reveal');}}
function finish(){if(disposed||finished.value)return;reveal();finished.value=true;cancelAnimationFrame(frame);later(()=>emit('done'),reducedMotion()?0:stage.value==='exit'?260:700);}

async function loadImages(){
  const urls=[...new Set(props.photos.filter(Boolean))].slice(0,8);
  return Promise.all(urls.map(src=>new Promise(resolve=>{const image=new Image();let settled=false;const done=value=>{if(settled)return;settled=true;resolve(value);};image.decoding='async';image.onload=()=>done(image);image.onerror=()=>done(null);later(()=>done(null),2500);image.src=src;}))).then(images=>images.filter(Boolean));
}

// Deterministic jitter so a resize re-lays the same shot instead of reshuffling it.
const noise=n=>{const s=Math.sin(n*12.9898)*43758.5453;return s-Math.floor(s);};
const expo=t=>t>=1?1:1-Math.pow(2,-10*t),inCubic=t=>t*t*t,clamp=t=>Math.min(1,Math.max(0,t));
const coverFit=(image,w,h)=>{const s=Math.max(w/image.naturalWidth,h/image.naturalHeight);return {s,ox:(image.naturalWidth*s-w)/2,oy:(image.naturalHeight*s-h)/2};};
const FONT='"Noto Serif SC","Source Han Serif SC","Songti SC","Microsoft YaHei",serif';

function paint(images){
  const el=canvas.value;if(!el||disposed||finished.value)return;cancelAnimationFrame(frame);
  const width=window.innerWidth,height=window.innerHeight,cx=width/2,cy=height*.47,dpr=Math.min(1.5,window.devicePixelRatio||1);
  el.width=Math.round(width*dpr);el.height=Math.round(height*dpr);el.style.width=width+'px';el.style.height=height+'px';
  const ctx=el.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);
  const cell=width<600?10:width<1100?13:16,gap=width<600?1:1.5,mask=document.createElement('canvas'),m=mask.getContext('2d',{willReadFrequently:true});mask.width=width;mask.height=height;
  const text=String(props.title||'林间笔记').trim().slice(0,24)||'林间笔记',fontSize=Math.max(56,Math.min(220,width*.22));
  m.font=`900 ${fontSize}px ${FONT}`;
  const scale=Math.min(1,width*.86/Math.max(1,m.measureText(text).width),height*.5/fontSize);
  m.font=`900 ${fontSize*scale}px ${FONT}`;m.textAlign='center';m.textBaseline='middle';m.fillStyle='#fff';m.fillText(text,cx,cy);
  const pixels=m.getImageData(0,0,width,height).data,targets=[];
  let minX=width,maxX=0,minY=height,maxY=0;
  for(let y=0;y<height;y+=cell)for(let x=0;x<width;x+=cell){const a=pixels[(Math.min(height-1,Math.round(y+cell/2))*width+Math.min(width-1,Math.round(x+cell/2)))*4+3];if(a>90){targets.push({x,y});minX=Math.min(minX,x);maxX=Math.max(maxX,x+cell);minY=Math.min(minY,y);maxY=Math.max(maxY,y+cell);}}
  if(!targets.length){finish();return;}

  // Shot 1: a quick montage of the frames. Shot 2: the last frame shatters and its pieces fly into the title.
  const montage=images.slice(-6),slot=150,montageEnd=montage.length*slot,buildEnd=montageEnd+2100,holdEnd=buildEnd+1100,exitEnd=holdEnd+950;
  const last=montage[montage.length-1],lastFit=last&&coverFit(last,width,height);
  // Each photo owns a vertical band of the title, so letters read as windows onto real frames.
  const bands=Math.max(1,images.length),bandW=(maxX-minX)/bands,boxH=maxY-minY;
  const fits=images.map((image,i)=>({image,bx:minX+i*bandW,...coverFit(image,bandW,boxH)}));
  const cols=Math.ceil(width/cell),rows=Math.ceil(height/cell);
  const tiles=targets.map((target,index)=>{
    const r1=noise(index+1),r2=noise(index+7.3),r3=noise(index+13.1),start=Math.floor(r2*cols*rows),sx=(start%cols)*cell,sy=Math.floor(start/cols)*cell;
    const fit=fits[Math.min(bands-1,Math.floor((target.x-minX)/Math.max(1,bandW)))];
    const to=fit?[fit.image,(target.x-fit.bx+fit.ox)/fit.s,(target.y-minY+fit.oy)/fit.s,cell/fit.s]:null;
    const from=lastFit?[last,(sx+lastFit.ox)/lastFit.s,(sy+lastFit.oy)/lastFit.s,cell/lastFit.s]:null;
    const dx=target.x-cx,dy=target.y-cy,len=Math.hypot(dx,dy)||1;
    return {sx,sy,rot:(r1-.5)*2.4,target,from,to,delay:((target.x-minX)/Math.max(1,maxX-minX))*.38+r3*.2,ux:dx/len,uy:dy/len,burst:.6+r1*.9,tone:`hsl(${28+r3*20} 32% ${78+r2*12}%)`};
  });
  const drawSrc=(src,size,alpha)=>{if(alpha<=.01)return;ctx.globalAlpha=alpha;const [image,x,y,s]=src;ctx.drawImage(image,x,y,s,s,-size/2,-size/2,size,size);};
  const drawFull=(image,zoom,alpha)=>{if(!image||alpha<=.01)return;const f=coverFit(image,width*zoom,height*zoom);ctx.globalAlpha=alpha;ctx.drawImage(image,(width-width*zoom)/2-f.ox,(height-height*zoom)/2-f.oy,image.naturalWidth*f.s,image.naturalHeight*f.s);};
  const begin=performance.now();stage.value=montage.length?'montage':'build';
  const draw=now=>{
    if(finished.value)return;
    const ms=now-begin;ctx.clearRect(0,0,width,height);ctx.globalAlpha=1;
    if(ms<montageEnd){
      const i=Math.floor(ms/slot),local=(ms%slot)/slot;
      drawFull(montage[i],1.16-.1*local,1);
      ctx.globalAlpha=Math.max(0,.35-local*.9);ctx.fillStyle='#fff';ctx.fillRect(0,0,width,height);
    }else if(ms<exitEnd){
      if(stage.value==='montage')stage.value='build';
      const t=clamp((ms-montageEnd)/(buildEnd-montageEnd)),exit=clamp((ms-holdEnd)/(exitEnd-holdEnd));
      if(ms>=holdEnd&&stage.value!=='exit'){stage.value='exit';reveal();}else if(ms>=buildEnd&&stage.value==='build')stage.value='hold';
      drawFull(last,1.06-.06*t,clamp(1-t*2.4));
      const x0=exit>0?inCubic(exit):0;
      for(const tile of tiles){
        const local=clamp((t-tile.delay)/.42),e=expo(local);
        let x=tile.sx+(tile.target.x-tile.sx)*e,y=tile.sy+(tile.target.y-tile.sy)*e,size=cell-gap*e,rot=tile.rot*Math.sin(Math.PI*local)*.6,alpha=1;
        if(x0){const push=x0*tile.burst*Math.max(width,height)*.7;x+=tile.ux*push;y+=tile.uy*push;size*=1+x0*3*tile.burst;rot+=tile.rot*x0;alpha=1-x0;}
        ctx.save();ctx.translate(x+cell/2,y+cell/2);if(rot)ctx.rotate(rot);
        if(tile.from)drawSrc(tile.from,size,alpha*(1-e));else if(e<1){ctx.globalAlpha=alpha*local;ctx.fillStyle=tile.tone;ctx.fillRect(-size/2,-size/2,size,size);}
        if(tile.to)drawSrc(tile.to,size,alpha*e);else if(e>0){ctx.globalAlpha=alpha*e;ctx.fillStyle=tile.tone;ctx.fillRect(-size/2,-size/2,size,size);}
        ctx.restore();
      }
      // Light sweep across the finished title; source-atop keeps it on the tiles only.
      const sweep=clamp((ms-buildEnd+200)/900);
      if(sweep>0&&sweep<1&&!x0){const sx=minX-200+(maxX-minX+400)*sweep,g=ctx.createLinearGradient(sx-120,0,sx+120,0);g.addColorStop(0,'#fff0');g.addColorStop(.5,'#fffc');g.addColorStop(1,'#fff0');ctx.globalCompositeOperation='source-atop';ctx.globalAlpha=.55;ctx.fillStyle=g;ctx.fillRect(minX-10,minY-10,maxX-minX+20,boxH+20);ctx.globalCompositeOperation='source-over';}
    }else{finish();return;}
    ctx.globalAlpha=1;frame=requestAnimationFrame(draw);
  };
  frame=requestAnimationFrame(draw);
}

onMounted(async()=>{
  later(finish,9500);
  try{
  const storage=props.replay==='once'?localStorage:sessionStorage;
  if(reducedMotion()||(props.replay!=='always'&&storage.getItem('lin-frame-intro-seen')==='1')){finish();return;}
  storage.setItem('lin-frame-intro-seen','1');await Promise.race([document.fonts.ready,new Promise(resolve=>later(resolve,1000))]);
  if(disposed||finished.value)return;
  const images=await loadImages();if(disposed||finished.value)return;paint(images);resizeHandler=()=>paint(images);window.addEventListener('resize',resizeHandler,{passive:true});
  keyHandler=event=>{if(event.key==='Escape')finish();};window.addEventListener('keydown',keyHandler);
  }catch{finish();}
});
onBeforeUnmount(()=>{disposed=true;cancelAnimationFrame(frame);for(const id of timers)clearTimeout(id);timers.clear();if(resizeHandler)window.removeEventListener('resize',resizeHandler);if(keyHandler)window.removeEventListener('keydown',keyHandler);});
</script>

<template>
  <Transition name="frame-intro">
    <div v-if="!finished" class="frame-intro" :data-stage="stage" role="region" aria-label="林间笔记片头" @click.self="finish">
      <canvas ref="canvas" aria-hidden="true"/>
      <i class="frame-bar top" aria-hidden="true"/><i class="frame-bar bottom" aria-hidden="true"/>
      <button type="button" class="frame-skip" @click="finish">跳过<span aria-hidden="true">→</span></button>
      <span class="frame-credit"><b/>A PERSONAL ARCHIVE<b/></span>
    </div>
  </Transition>
</template>

<style scoped>
.frame-intro{position:fixed;inset:0;z-index:9999;overflow:hidden;background-color:#0d0c0b;color:#f3ede4;transition:background-color .9s ease}
.frame-intro::after{content:"";position:absolute;inset:0;pointer-events:none;background:radial-gradient(90% 70% at 50% 47%,transparent 55%,#000a 100%);transition:opacity .6s}
.frame-intro[data-stage=exit]{background-color:transparent}
.frame-intro[data-stage=exit]::after{opacity:0}
.frame-intro canvas{position:absolute;inset:0;width:100%;height:100%;transform-origin:50% 47%;transition:transform 1.4s cubic-bezier(.2,.6,.2,1)}
.frame-intro[data-stage=hold] canvas{transform:scale(1.04)}
.frame-bar{position:absolute;left:0;right:0;z-index:1;height:9vh;background:#050505;transition:transform .9s cubic-bezier(.65,0,.35,1)}
.frame-bar.top{top:0;transform:translateY(-100%)}.frame-bar.bottom{bottom:0;transform:translateY(100%)}
.frame-intro:is([data-stage=montage],[data-stage=build],[data-stage=hold]) .frame-bar{transform:none}
.frame-skip{position:absolute;top:calc(9vh + 18px);right:clamp(16px,3vw,36px);z-index:2;display:inline-flex;align-items:center;gap:8px;padding:8px 2px;border:0;border-bottom:1px solid #f3ede455;background:none;color:#f3ede4cc;font-size:12px;letter-spacing:3px;cursor:pointer;transition:color .2s,border-color .2s,opacity .4s;text-shadow:0 1px 8px #000a}
.frame-skip:hover,.frame-skip:focus-visible{color:#fff;border-color:#fff;outline:none}
.frame-skip span{transition:transform .2s}.frame-skip:hover span{transform:translateX(3px)}
.frame-intro[data-stage=exit] .frame-skip{opacity:0}
.frame-credit{position:absolute;bottom:calc(9vh + 22px);left:50%;z-index:2;display:flex;align-items:center;gap:14px;transform:translateX(-50%);font-size:10px;letter-spacing:5px;white-space:nowrap;opacity:0;transition:opacity .8s}
.frame-credit b{width:28px;height:1px;background:currentColor;opacity:.5}
.frame-intro[data-stage=hold] .frame-credit{opacity:.75}
.frame-intro-leave-active{transition:opacity .7s ease}
.frame-intro-leave-to{opacity:0}
.frame-intro[data-stage=exit].frame-intro-leave-active{transition-duration:.26s}
@media(max-width:600px){.frame-bar{height:7vh}.frame-skip{top:calc(7vh + 12px)}.frame-credit{bottom:calc(7vh + 16px);letter-spacing:3px}}
@media(prefers-reduced-motion:reduce){.frame-intro,.frame-intro-leave-active,.frame-intro canvas,.frame-bar{transition:none}}
</style>
