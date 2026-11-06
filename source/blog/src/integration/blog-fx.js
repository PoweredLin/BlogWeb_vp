// Decorative motion for the public blog: scroll reveal, card tilt, magnetic buttons, cursor ring, click sparks.
// Everything is skipped under prefers-reduced-motion or when the site turns motion off (data-blog-motion=false).
const root=document.documentElement;
const reduced=()=>matchMedia('(prefers-reduced-motion: reduce)').matches||root.dataset.blogMotion==='false';
const finePointer=matchMedia('(hover:hover) and (pointer:fine)').matches;
const REVEAL='.editorial-row,.lin-section-heading,.home-extra,.right-side .el-card,.lin-footer>*,.lin-ticker';
const MAGNETIC='.lin-primary,.lin-random,.lin-write,.poster-dots button';

let batch=0,batchTimer=0;
const io='IntersectionObserver' in window?new IntersectionObserver(entries=>{
  for(const entry of entries){
    if(!entry.isIntersecting)continue;
    const el=entry.target;io.unobserve(el);
    // Elements revealed in the same frame cascade instead of popping in together.
    el.style.setProperty('--fx-d',Math.min(batch++,6)*90+'ms');
    clearTimeout(batchTimer);batchTimer=setTimeout(()=>{batch=0;},120);
    requestAnimationFrame(()=>{el.classList.add('fx-in');el.classList.remove('fx-wait');});
  }
},{rootMargin:'0px 0px -8% 0px',threshold:.08}):null;

function scan(node){
  if(!io||reduced()||!(node instanceof Element))return;
  const list=node.matches?.(REVEAL)?[node]:[];
  list.push(...node.querySelectorAll(REVEAL));
  for(const el of list){if(el.classList.contains('fx-in')||el.classList.contains('fx-wait'))continue;el.classList.add('fx-wait');io.observe(el);}
}

function tilt(event){
  const card=event.target.closest?.('.editorial-link');if(!card)return;
  const r=card.getBoundingClientRect(),x=(event.clientX-r.left)/r.width,y=(event.clientY-r.top)/r.height;
  card.style.setProperty('--mx',x*100+'%');card.style.setProperty('--my',y*100+'%');
  card.style.setProperty('--ry',(x-.5)*7+'deg');card.style.setProperty('--rx',(.5-y)*6+'deg');
}
function untilt(event){const card=event.target.closest?.('.editorial-link');if(card&&!card.contains(event.relatedTarget)){card.style.removeProperty('--rx');card.style.removeProperty('--ry');}}

function magnet(event){
  const el=event.target.closest?.(MAGNETIC);if(!el)return;
  const r=el.getBoundingClientRect();
  el.style.translate=`${(event.clientX-r.left-r.width/2)*.22}px ${(event.clientY-r.top-r.height/2)*.3}px`;
}
function unmagnet(event){const el=event.target.closest?.(MAGNETIC);if(el&&!el.contains(event.relatedTarget))el.style.translate='';}

function cursor(){
  const dot=document.createElement('i'),ring=document.createElement('i');
  dot.className='fx-cursor-dot';ring.className='fx-cursor-ring';document.body.append(dot,ring);
  let tx=-100,ty=-100,rx=-100,ry=-100,frame=0;
  const loop=()=>{rx+=(tx-rx)*.18;ry+=(ty-ry)*.18;ring.style.transform=`translate(${rx}px,${ry}px)`;frame=Math.abs(tx-rx)+Math.abs(ty-ry)>.3?requestAnimationFrame(loop):0;};
  addEventListener('pointermove',e=>{
    if(reduced()||e.pointerType!=='mouse'){root.classList.remove('fx-cursor-on');return;}
    root.classList.add('fx-cursor-on');tx=e.clientX;ty=e.clientY;dot.style.transform=`translate(${tx}px,${ty}px)`;
    ring.classList.toggle('is-link',!!e.target.closest?.('a,button,[role=button],.editorial-link'));
    if(!frame)frame=requestAnimationFrame(loop);
  },{passive:true});
  document.addEventListener('pointerleave',()=>root.classList.remove('fx-cursor-on'));
}

const SPARKS=['✦','✧','•','✦','❀'];
function spark(event){
  if(reduced()||event.button!==0||!event.isPrimary)return;
  for(let i=0;i<7;i++){
    const s=document.createElement('i'),angle=Math.PI*2*i/7+Math.random()*.5,dist=26+Math.random()*30;
    s.className='fx-spark';s.textContent=SPARKS[i%SPARKS.length];s.style.left=event.clientX+'px';s.style.top=event.clientY+'px';
    s.style.color=i%2?'var(--lin-gold)':'var(--lin-accent)';document.body.append(s);
    s.animate([{transform:'translate(-50%,-50%) scale(.4)',opacity:1},{transform:`translate(calc(-50% + ${Math.cos(angle)*dist}px),calc(-50% + ${Math.sin(angle)*dist}px)) scale(1) rotate(${(Math.random()-.5)*180}deg)`,opacity:0}],{duration:620+Math.random()*200,easing:'cubic-bezier(.2,.7,.3,1)'}).onfinish=()=>s.remove();
  }
}

export function startBlogFx(){
  scan(document.body);
  new MutationObserver(records=>{for(const r of records)for(const n of r.addedNodes)scan(n);}).observe(document.body,{childList:true,subtree:true});
  addEventListener('pointerdown',spark,{passive:true});
  if(!finePointer)return;
  document.addEventListener('pointermove',e=>{if(reduced())return;tilt(e);magnet(e);},{passive:true});
  document.addEventListener('pointerout',e=>{untilt(e);unmagnet(e);},{passive:true});
  cursor();
}
