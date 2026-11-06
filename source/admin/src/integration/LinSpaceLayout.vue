<script setup lang="ts">
import {ref,computed,watch,onMounted,onBeforeUnmount} from 'vue';import {useRoute} from 'vue-router';import {useUserStoreHook} from '@/store/modules/user';import {request} from './service';import LinIcon from './LinIcon.vue';import './space.scss';import './space-v8.scss';import './space-shell.scss';import './space-modules.scss';
const route=useRoute(),me=useUserStoreHook(),theme=ref('minimal'),wallpaper=ref('/assets/landscape-study.webp'),opacity=ref(.24),motion=ref(true),open=ref(false),notice=ref('');
const groups=[{id:'room',path:'/room',label:'据点',hint:'HOME BASE',icon:'home'},{id:'write',path:'/article/articleList',label:'写作台',hint:'WRITING',icon:'pen'},{id:'shelf',path:'/life/library',label:'收藏架',hint:'COLLECTION',icon:'heart'},{id:'daily',path:'/life/tasks',label:'日常支线',hint:'SIDE QUESTS',icon:'clock'},{id:'tools',path:'/features',label:'工具箱',hint:'TOOLS',icon:'grid'},{id:'site',path:'/management',label:'站务',hint:'SITE',icon:'settings'}];
const featurePaths=['/api-reference','/features','/content-import','/documents','/reference-docs','/automation','/mail-settings','/appearance','/life/settings'];const adminPaths=['/page-layout','/anime-wall','/management','/comments','/registrations','/taxonomy','/authors','/site-settings','/access-tokens'];
const section=computed(()=>route.path.startsWith('/article')||['/moments','/albums'].includes(route.path)?'write':featurePaths.includes(route.path)?'tools':adminPaths.includes(route.path)?'site':route.path==='/life/library'?'shelf':route.path.startsWith('/life')?'daily':route.path==='/profile'?'profile':'room');
const subs={write:[['/article/articleList','文章'],['/article/addArticle','写文章'],['/moments','说说'],['/albums','相册']],site:[['/management','站务概览'],['/page-layout','首页与片头'],['/anime-wall','番剧公开'],['/comments','评论审核'],['/registrations','注册审核'],['/taxonomy','分类标签'],['/authors','读者账号'],['/site-settings','站点设置'],['/access-tokens','访问凭证']],tools:[['/features','总览'],['/api-reference','API 接入'],['/automation','自动化'],['/mail-settings','邮件推送'],['/documents','私有文档'],['/reference-docs','开发书架'],['/content-import','JSON 导入'],['/appearance','空间外观'],['/life/settings','日常偏好']]};
const sub=computed(()=>subs[section.value]||[]);
const current=computed(()=>groups.find(g=>g.id===section.value)||{label:'个人设置',hint:'PROFILE'});
const pageTitle=computed(()=>sub.value.find(([path])=>path===route.path)?.[1]||String(route.meta?.title||current.value.label));
const cozy=computed(()=>theme.value==='cozy');
async function load(){const p=await request('/api/studio/profile');theme.value=p.theme;wallpaper.value=p.customWallpaper||'/assets/'+p.wallpaper+'.webp';opacity.value=(p.wallpaperOpacity??24)/100;motion.value=p.motion!==false;}
async function toggle(){try{const p=await request('/api/studio/profile');p.theme=theme.value==='cozy'?'minimal':'cozy';await request('/api/studio/profile','PUT',p);theme.value=p.theme;window.dispatchEvent(new CustomEvent('lin-theme',{detail:p.theme}));}catch(e){notice.value=e.message;}}
watch(()=>route.path,()=>{open.value=false;appearance();});
// Teleported Element Plus overlays live outside the shell, so mirror the theme onto <html>.
watch(theme,value=>{document.documentElement.dataset.spaceTheme=value;},{immediate:true});
function changed(e){theme.value=e.detail;}function appearance(){load().catch(e=>notice.value=e.message);}onMounted(()=>{appearance();addEventListener('lin-theme',changed);addEventListener('lin-appearance',appearance);});onBeforeUnmount(()=>{delete document.documentElement.dataset.spaceTheme;removeEventListener('lin-theme',changed);removeEventListener('lin-appearance',appearance);});
</script>
<template><div class="space-shell v10" :class="{'nav-open':open}" :data-theme="theme" :data-motion="motion" :style="{'--room-wallpaper':'url('+wallpaper+')','--wallpaper-opacity':opacity}">
 <header class="space-bar">
  <RouterLink to="/room" class="space-logo"><span>L✦</span><div>林间笔记<small>{{cozy?'私宅 · SAVE POINT':'工作室 · STUDIO'}}</small></div></RouterLink>
  <a href="/" class="space-home space-home-compact" aria-label="回到首页"><LinIcon name="home" :size="18"/></a>
  <button class="space-nav-toggle" @click="open=!open" :aria-expanded="open" aria-label="展开空间导航"><LinIcon name="menu"/></button>
  <RouterLink to="/article/addArticle" class="space-compose"><LinIcon name="pen" :size="20"/>写文章</RouterLink>
  <nav :class="{open}" aria-label="空间导航"><RouterLink v-for="g in groups" :key="g.id" :to="g.path" :class="{selected:section===g.id}"><LinIcon :name="g.icon" :size="17"/><span>{{g.label}}<small>{{g.hint}}</small></span></RouterLink></nav>
  <div class="space-controls">
   <a href="/" class="space-home"><LinIcon name="home" :size="16"/><span>回到首页</span><b aria-hidden="true">↗</b></a>
   <button @click="toggle" class="space-theme" :aria-label="'切换到'+(cozy?'工作室':'私宅')+'主题'"><i aria-hidden="true"/><span>{{cozy?'私宅':'工作室'}}</span></button>
   <RouterLink to="/profile" class="space-avatar" aria-label="个人设置"><img :src="me.avatar||'/favicon.svg'" alt="我的头像"/></RouterLink>
   <button class="space-logout" @click="me.logOut()" aria-label="退出登录"><LinIcon name="logout" :size="16"/></button>
  </div>
 </header>
 <button v-if="open" class="space-scrim" aria-label="关闭导航" @click="open=false"/>
 <div class="space-stage">
  <div class="space-context"><div class="space-heading"><span>{{current.hint}} <i>/</i> {{current.label}}</span><h1>{{pageTitle}}</h1></div><div><RouterLink v-if="section!=='site'" to="/appearance">空间外观</RouterLink><span class="space-greet">{{me.nick_name||'Lin'}}，{{cozy?'欢迎回家':'开始工作吧'}}</span></div></div>
  <nav v-if="sub.length" class="space-subnav"><RouterLink v-for="[path,label] in sub" :key="path" :to="path" :class="{current:route.path===path}">{{label}}</RouterLink></nav>
  <p v-if="notice" class="space-notice" role="status">{{notice}}<button @click="notice=''" aria-label="关闭提示">×</button></p>
  <main class="space-body admin-content"><RouterView v-slot="{Component}"><Transition name="room-page" mode="out-in"><component :is="Component" :key="route.fullPath"/></Transition></RouterView></main>
  <footer class="space-bottom"><span>林间笔记</span><span>{{cozy?'认真喜欢，也好好生活。':'留一点空间，给下一次灵感。'}}</span><a href="/">回到首页</a><a href="/about">关于</a></footer>
 </div>
</div></template>
