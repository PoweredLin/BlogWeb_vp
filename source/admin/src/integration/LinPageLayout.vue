<script setup lang="ts">
import {computed,onMounted,ref} from 'vue';
import {request,upload} from './service';
import LinFrameIntro from '../../../blog/src/integration/LinFrameIntro.vue';

const form=ref<any>(null),busy=ref(false),notice=ref(''),preview=ref(false);
const labels={profile:'站主介绍',anime:'季度番剧',web:'内嵌开发文档',articles:'文章列表',moments:'近期说说',albums:'相册精选',stage:'欢迎舞台与角色',stats:'草稿与任务统计',progress:'进行中与下一站',shelf:'兴趣收藏架',git:'Git 动态'};
const library=ref<any[]>([]),site=ref<any>({}),media=ref<any[]>([]),books=ref<any[]>([]),mediaPage=ref(1),mediaMore=ref(false),mediaQuery=ref('');
async function loadMedia(reset=false){if(reset)mediaPage.value=1;const r=await request('/api/private/media?pageSize=24&page='+mediaPage.value+'&q='+encodeURIComponent(mediaQuery.value));media.value=reset?r.items:[...media.value,...r.items];mediaMore.value=r.hasMore;mediaPage.value++;}
const choices=computed(()=>{
 const anime=library.value.filter(item=>item.kind==='番剧'&&item.cover).map(item=>({url:item.cover,title:item.title,group:'已收藏番剧'}));
 const hero=(site.value.heroImages||[]).map((key:string)=>({url:key.startsWith('/')?key:'/assets/'+key+'.webp',title:'首页轮播图',group:'首页图片'}));
 const selected=(form.value?.introPhotos||[]).map((url:string)=>({url,title:'精选素材',group:'已选图片'}));
 return [...new Map([...selected,...anime,...hero,...media.value.map(item=>({url:item.url,title:item.name,group:'素材库'}))].map(item=>[item.url,item])).values()];
});
const atLimit=computed(()=>form.value?.introPhotos?.length>=18);

async function load(){
 const [layout,state,settings,docs]=await Promise.all([request('/api/private/page-layout'),request('/api/private/catalog/records/library?subtype='+encodeURIComponent('番剧')+'&pageSize=24'),request('/api/site'),request('/api/private/reference-docs')]);
 form.value=layout;library.value=state.items;site.value=settings||{};books.value=docs.items.filter(item=>item.public);await loadMedia(true);
}
function move(section:string,index:number,delta:number){
 const list=form.value[section];if(index+delta<0||index+delta>=list.length)return;
 [list[index],list[index+delta]]=[list[index+delta],list[index]];
}
function togglePhoto(url:string){
 form.value.introPhotoMode='custom';
 const photos=form.value.introPhotos;
 if(photos.includes(url))form.value.introPhotos=photos.filter((item:string)=>item!==url);
 else if(photos.length>=18)notice.value='片头素材最多选择 18 张。';
 else form.value.introPhotos=[...photos,url];
}
async function addUpload(event:any){
 const input=event.target,file=input.files?.[0];input.value='';if(!file)return;
 if(atLimit.value){notice.value='片头素材最多选择 18 张。';return;}
 busy.value=true;
 try{const result=await upload(file),url=result.result.url;if(!form.value.introPhotos.includes(url))form.value.introPhotos.push(url);form.value.introPhotoMode='custom';notice.value='图片已加入精选；保存布局后才会公开用于片头。';}
 catch(e:any){notice.value=e.message||'图片上传失败';}finally{busy.value=false;}
}
async function save(){
 busy.value=true;
 try{form.value=await request('/api/private/page-layout','PUT',form.value);notice.value='布局已保存，刷新页面后生效。';}
 catch(e:any){notice.value=e.message||'保存失败';}finally{busy.value=false;}
}
async function reset(){
 if(!confirm('恢复默认页面模块和片头配置？'))return;
 busy.value=true;
 try{form.value=await request('/api/private/page-layout/reset','POST',{version:form.value.version});notice.value='已恢复默认布局。';}
 catch(e:any){notice.value=e.message||'恢复默认布局失败';}finally{busy.value=false;}
}
onMounted(()=>load().catch((e:any)=>notice.value=e.message||'页面布局读取失败'));
</script>
<template>
 <section class="layout-page">
  <header><span class="space-eyebrow">MAKE IT YOURS / MODULES</span><h1>把页面布置成你的习惯。</h1><p>调整模块显示、顺序、强调色与片头。功能通过版本更新，不开放脚本或自定义代码。</p></header>
  <form v-if="form" @submit.prevent="save">
   <div class="module-columns">
    <section v-for="section in ['home','room']" :key="section"><h2>{{section==='home'?'公开首页':'私人房间'}}</h2><p>{{section==='home'?'仅从已公开内容中读取。':'仅站主可见，不会发布到博客。'}}</p><article v-for="(row,index) in form[section]" :key="row.id"><el-switch v-model="row.enabled" :disabled="row.id==='articles'" :aria-label="labels[row.id]"/><strong>{{labels[row.id]}}</strong><button type="button" :disabled="index===0" :aria-label="'上移'+labels[row.id]" @click="move(section,index,-1)">↑</button><button type="button" :disabled="index===form[section].length-1" :aria-label="'下移'+labels[row.id]" @click="move(section,index,1)">↓</button></article></section>
   </div>
   <section class="layout-options"><h2>整体偏好</h2><label>强调色<el-select v-model="form.accent"><el-option v-for="(name,key) in {violet:'淡紫',forest:'松绿',ocean:'海蓝',rose:'蔷薇'}" :key="key" :label="name" :value="key"/></el-select></label><label><el-switch v-model="form.animeAutoPublic"/>公开展示已确认采集的新番</label><p>仅公开采集作品的标题、封面和播出信息；收藏笔记和进度仍为私有。首页“季度番剧”模块可单独启用或关闭。</p><label>首页番剧数量<el-input-number v-model="form.animeLimit" :min="1" :max="24"/></label><label>首页季度（auto 或 2026-Q4）<el-input v-model="form.animeSeason" maxlength="7"/></label><label>首页文档<el-select v-model="form.webDocumentId"><el-option label="第一个已公开书签" value=""/><el-option v-for="doc in books" :key="doc.id" :label="doc.title" :value="doc.id"/></el-select></label><p>书签需先在功能 → 开发书架勾选“允许首页公开”。</p><label><el-switch v-model="form.introEnabled"/>启用照片拼字片头</label><label>片头播放频率<el-select v-model="form.introReplay"><el-option label="每个浏览会话一次" value="session"/><el-option label="每次打开首页" value="always"/><el-option label="每台设备一次" value="once"/></el-select></label>
    <div class="intro-source"><h3>拼字画报素材</h3><label>片头文字（留空使用网站名称）<el-input v-model="form.introTitle" maxlength="24" placeholder="林间笔记"/></label><p>自动模式沿用首页轮播图和已公开文章封面。精选模式只展示你勾选的图片；上传图片加入精选并保存后，才会公开访问。</p><el-radio-group v-model="form.introPhotoMode"><el-radio value="auto">自动沿用</el-radio><el-radio value="custom">手动精选</el-radio></el-radio-group>
     <div class="media-search"><el-input v-model="mediaQuery" placeholder="按文件名搜索素材" clearable @keyup.enter="loadMedia(true)"/><el-button @click="loadMedia(true)">搜索素材</el-button></div><div class="photo-picker"><button v-for="item in choices" :key="item.url" type="button" :class="{chosen:form.introPhotos.includes(item.url)}" @click="togglePhoto(item.url)"><img :src="item.url" :alt="item.title"/><span>{{item.title}}</span><i>{{form.introPhotos.includes(item.url)?'已选':'选择'}}</i></button><label class="upload-photo" :class="{disabled:atLimit||busy}"><input type="file" accept="image/png,image/jpeg,image/webp" :disabled="atLimit||busy" @change="addUpload"/><b>{{busy?'…':'+'}}</b><span>{{atLimit?'已达 18 张上限':'上传图片'}}</span></label></div>
     <el-button v-if="mediaMore" @click="loadMedia()">更多素材</el-button><el-button type="primary" plain @click="preview=true">预览当前片头</el-button><p v-if="form.introPhotoMode==='custom'" class="photo-count">已选 {{form.introPhotos.length}} / 18 张</p>
     <ol v-if="form.introPhotoMode==='custom'" class="selected-photos"><li v-for="(url,index) in form.introPhotos" :key="url"><img :src="url" alt="已选片头素材"/><span>画报 {{index+1}}</span><el-button :disabled="index===0" @click="move('introPhotos',index,-1)">上移</el-button><el-button :disabled="index===form.introPhotos.length-1" @click="move('introPhotos',index,1)">下移</el-button><el-button @click="togglePhoto(url)">移除</el-button></li></ol>
    </div>
   </section>
   <footer><span role="status">{{notice}}</span><el-button :disabled="busy" @click="reset">恢复默认</el-button><el-button type="primary" native-type="submit" :loading="busy">保存页面布局</el-button></footer>
  </form>
  <LinFrameIntro v-if="preview && form" :title="form.introTitle||site.title||'林间笔记'" :photos="form.introPhotoMode==='custom'?form.introPhotos:choices.map(item=>item.url)" replay="always" @done="preview=false"/>
 </section>
</template>
<style scoped>
.selected-photos{padding:0;list-style:none;display:grid;gap:10px}.selected-photos li{display:flex;align-items:center;gap:10px}.selected-photos img{width:60px;height:45px;object-fit:cover;border-radius:5px}.selected-photos span{flex:1;font-size:12px}
.layout-page{max-width:1120px;margin:auto}.layout-page h1{font-size:28px;margin:12px 0}.layout-page p{font-size:12px;line-height:1.8;color:var(--studio-muted)}.module-columns{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-top:28px}.module-columns>section,.layout-options{padding:25px;background:var(--studio-panel);border:1px solid var(--studio-line);border-radius:8px}.layout-page h2{font-size:19px;margin:0 0 12px}.module-columns article{display:flex;align-items:center;gap:12px;border-top:1px solid var(--studio-line);padding:14px 0}.module-columns strong{font-size:12px;flex:1}.module-columns button{padding:5px 10px;background:var(--studio-bg);color:inherit;border:1px solid var(--studio-line);border-radius:4px;cursor:pointer}.module-columns button:disabled{opacity:.3;cursor:default}.layout-options{margin-top:24px}.layout-options>label{display:flex;gap:12px;align-items:center;font-size:12px;margin:18px 0}.layout-options .el-select{max-width:260px}.intro-source{border-top:1px solid var(--studio-line);margin-top:22px;padding-top:20px}.intro-source h3{font-size:15px;margin:0}.intro-source>p{max-width:760px}.photo-picker{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:12px;margin-top:16px}.photo-picker>button,.upload-photo{min-width:0;position:relative;display:grid;gap:7px;padding:7px;text-align:left;color:inherit;background:var(--studio-bg);border:1px solid var(--studio-line);border-radius:6px;cursor:pointer}.photo-picker>button.chosen{border-color:#8273a6;box-shadow:0 0 0 1px #8273a6}.photo-picker img{width:100%;height:120px;object-fit:cover;border-radius:3px}.photo-picker span,.photo-picker i,.upload-photo span{font-size:11px;font-style:normal}.photo-picker i{position:absolute;right:11px;top:11px;padding:4px 6px;background:#111b;color:#fff;border-radius:3px}.upload-photo{place-items:center;align-content:center;min-height:170px;border-style:dashed}.upload-photo b{font-size:30px;font-weight:400}.upload-photo input{position:absolute;inset:0;width:100%;height:100%;opacity:0;cursor:pointer}.upload-photo.disabled{opacity:.45;cursor:not-allowed}.upload-photo input:disabled{cursor:not-allowed}.photo-count{font-variant-numeric:tabular-nums}.layout-page footer{display:flex;align-items:center;justify-content:flex-end;gap:12px;padding:24px 0}.layout-page footer span{margin-right:auto;font-size:12px}@media(max-width:720px){.module-columns{grid-template-columns:1fr}.layout-page h1{font-size:24px}.module-columns>section,.layout-options{padding:18px}.layout-page footer{flex-wrap:wrap}}
</style>
