import {spawnSync} from 'node:child_process';
import fs from 'node:fs';import path from 'node:path';

/* 发布用的唯一入口：npm run build（= node scripts/build.mjs）。
 注意不要拿 npm run dev:web 的输出打包：vite 在 --watch 模式下不会清空 outDir，
 每次重建都会在 assets/ 里留下一份上一代的 hash 文件。V7 就是这么堆出 51MB 历史产物的。
 这里在每次构建前显式清掉目标目录，构建后再做一次"入口可达性"检查兜底。 */
const OUT={tools:'public/tools-app',blog:'public/blog-app',admin:'public/admin-app'};

/* Windows 上 fs.rmSync(recursive) 有静默失效的情况（返回成功但目录没删掉），
 所以这里手写递归删除，逐条 unlink 再 rmdir，删完必须复核。 */
function removeDir(dir){
 if(!fs.existsSync(dir))return;
 for(const entry of fs.readdirSync(dir,{withFileTypes:true})){
  const p=path.join(dir,entry.name);
  if(entry.isDirectory()){removeDir(p);continue;}
  try{fs.unlinkSync(p);}catch{fs.chmodSync(p,0o666);fs.unlinkSync(p);}
 }
 fs.rmdirSync(dir);
}

for(const target of ['blog','admin','tools']){
 const dist=path.resolve(OUT[target]);
 removeDir(dist);
 if(fs.existsSync(dist)){console.error(`无法清空 ${OUT[target]}，构建中止以免产出混入旧文件。`);process.exit(1);}
 const args=['node_modules/vite/bin/vite.js','build','--config',target==='tools'?'vite.tools.config.mjs':'vite.source.config.mjs'];
 const r=spawnSync(process.execPath,args,{stdio:'inherit',env:{...process.env,BUILD_TARGET:target}});
 if(r.status!==0)process.exit(r.status||1);
}

function walkFrom(dir){
 const entry=path.join(dir,'index.html');
 if(!fs.existsSync(entry))return null;
 const base=path.join(dir,'assets');
 if(!fs.existsSync(base))return null;
 const seen=new Set([...fs.readFileSync(entry,'utf8').matchAll(/assets\/([A-Za-z0-9_.\-]+)/g)].map(m=>m[1]));
 const queue=[...seen];
 while(queue.length){
  const file=queue.pop(),p=path.join(base,file);
  if(!fs.existsSync(p))continue;
  for(const m of fs.readFileSync(p,'utf8').matchAll(/(?:[/"'])([A-Za-z0-9_.\-]+\.(?:js|css|woff2?|ttf|svg|png|webp))/g)){
   const n=m[1];
   if(!seen.has(n)&&fs.existsSync(path.join(base,n))){seen.add(n);queue.push(n);}
  }
 }
 return {base,files:fs.readdirSync(base).filter(f=>fs.statSync(path.join(base,f)).isFile()),seen};
}

let leftover=0;
for(const target of ['blog','admin','tools']){
 const r=walkFrom(path.resolve(OUT[target]));
 if(!r)continue;
 const stale=r.files.filter(f=>!r.seen.has(f));
 leftover+=stale.length;
 const mb=(stale.reduce((n,f)=>n+fs.statSync(path.join(r.base,f)).size,0)/1048576).toFixed(1);
 console.log(`[${target}] assets: ${r.files.length} 个文件，入口可达 ${r.files.length-stale.length} 个${stale.length?`，残留 ${stale.length} 个 / ${mb} MB`:'，无残留'}`);
}
if(leftover)console.warn('警告：构建产物里还有没被任何入口引用到的文件，打包上传前请先确认来源。');
