import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
const dir=fs.mkdtempSync(path.join(os.tmpdir(),'site-status-')),origin='http://127.0.0.1:4352';
const server=spawn('.venv/Scripts/python.exe',['-m','backend.run'],{env:{...process.env,APP_ENV:'development',COOKIE_SECURE:'false',DATA_DIR:dir,HOST:'127.0.0.1',PORT:'4352',SITE_URL:origin},stdio:'pipe'});
for(let n=0;n<100;n++){try{if((await fetch(origin+'/healthz')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
const write=async(url,data,method='POST')=>{const r=await fetch(origin+url,{method,headers:{Origin:origin,'Content-Type':'application/json',Cookie:session},body:JSON.stringify(data)});assert(r.ok,await r.clone().text());return r.json();};
let session='';
const setup=await fetch(origin+'/api/setup',{method:'POST',headers:{Origin:origin,'Content-Type':'application/json'},body:JSON.stringify({name:'Lin',password:'site-test-password',demo:false})});assert(setup.ok);session=setup.headers.get('set-cookie').split(';')[0];
for(let i=0;i<10;i++)await write('/api/private/records/library',{title:'Poster '+i,kind:'番剧',status:'wish',progress:0,total:12,cover:'/assets/landscape-dawn.webp',season:`${new Date().getFullYear()}-Q${Math.floor(new Date().getMonth()/3)+1}`,public:true});
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'C:/Users/JLZ/.agent-browser/browsers/chrome-153.0.8010.36/chrome.exe'});
try{
 const context=await browser.newContext({viewport:{width:1113,height:902},reducedMotion:'reduce'});
 const page=await context.newPage(),errors=[],externalFonts=[];let checks=0;
 page.on('pageerror',e=>errors.push(e.message));
 page.on('request',r=>{if(/fonts\.google|fonts\.gstatic|cdn.*woff/.test(r.url()))externalFonts.push(r.url());if(r.url().endsWith('/api/public/status'))checks++;});
 await page.goto('http://127.0.0.1:4352/home');
 await page.locator('.lin-footer .service-check[data-state=online]').waitFor();
 await page.locator('.home-posters>a').nth(9).waitFor();
 assert.equal(await page.locator('.home-posters>a').count(),10);
 assert.equal(await page.locator('.right-side .info-avatar img').getAttribute('src'),'/favicon.svg');
 assert.equal(checks,1);
 assert(await page.evaluate(async()=>{await document.fonts.load('400 16px Inter');await document.fonts.load('700 20px Lora');return document.fonts.check('400 16px Inter')&&document.fonts.check('700 20px Lora');}));
 for(const theme of ['paper','gallery'])for(const dark of [false,true]){
  await page.evaluate(({theme,dark})=>{document.documentElement.dataset.blogTheme=theme;document.documentElement.classList.toggle('dark',dark);},{theme,dark});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 }
 await page.locator('.right-side').scrollIntoViewIfNeeded();
 await page.screenshot({path:'data/site-release-sidebar.png'});
 await page.locator('.lin-footer').scrollIntoViewIfNeeded();await page.screenshot({path:'data/site-release-footer.png'});
 await page.goto('http://127.0.0.1:4352/about');
 await page.getByRole('heading',{name:'林间笔记，给日常留一个位置。'}).waitFor();
 assert.equal(await page.getByText('author 管理自己的文章',{exact:false}).count(),0);
 await page.locator('#references summary').click();assert(await page.getByRole('link',{name:'博客来源许可'}).isVisible());
 await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 await page.screenshot({path:'data/site-release-about-mobile.png',fullPage:true});
 // Simulate a failed health request and a known start date in isolated contexts.
 for(const ok of [false,true]){
  const c=await browser.newContext({reducedMotion:'reduce'});await c.route('**/api/public/status',route=>ok?route.fulfill({json:{ok:true,siteStartedAt:'2026-01-01T00:00:00+08:00'}}):route.abort());
  const p=await c.newPage();await p.goto('http://127.0.0.1:4352/home');
  if(ok)await p.locator('.lin-footer .site-runtime').filter({hasText:/已相伴 \d+ 天/}).waitFor();
  else await p.locator('.lin-footer .service-check[data-state=unavailable]').waitFor();
  await c.close();
 }
 assert.deepEqual(errors,[]);assert.deepEqual(externalFonts,[]);
 console.log('PASS status deduplication/failure/runtime, local fonts, logo, 10 posters, themes, mobile, about and licenses');
}finally{await browser.close();server.kill();}
