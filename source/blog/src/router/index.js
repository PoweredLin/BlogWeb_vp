import NProgress from 'nprogress';import 'nprogress/nprogress.css';import {createRouter,createWebHistory} from 'vue-router';import Layout from '@/components/Layout/index.vue';
const routes=[{path:'/',component:Layout,children:[
 {path:'',redirect:'/home'},
 {path:'home',name:'Home',meta:{name:'首页'},component:()=>import('@/views/home/home.vue')},
 {path:'archives',alias:'/archive',name:'Archives',meta:{name:'时间轴'},component:()=>import('@/views/archives/archives.vue')},
 {path:'category',alias:'/categories',name:'Category',meta:{name:'分类'},component:()=>import('@/views/category/category.vue')},
 {path:'tag',name:'Tag',meta:{name:'标签'},component:()=>import('@/views/tag/tag.vue')},
 {path:'article',name:'Article',meta:{name:'文章'},component:()=>import('@/integration/LinReading.vue')},
 {path:'blog/:slug',redirect:to=>({path:'/article',query:{id:to.params.slug}})},
 {path:'articleList',name:'ArticleList',meta:{name:'文章列表'},component:()=>import('@/views/article/article-list.vue')},
 {path:'moments',name:'Moments',meta:{name:'说说'},component:()=>import('@/integration/LinJournal.vue')},
 {path:'albums',name:'Albums',meta:{name:'相册'},component:()=>import('@/integration/LinJournal.vue')},
 {path:'about',name:'About',meta:{name:'关于网站'},component:()=>import('@/views/about.vue')},
 {path:':pathMatch(.*)*',component:()=>import('@/views/404/index.vue')}]}];
const router=createRouter({history:createWebHistory(),routes});router.beforeEach(()=>{NProgress.start();});router.afterEach(to=>{NProgress.done();document.title=(to.meta.name||'博客')+' · Lin 的随手记';if(!to.hash)window.scrollTo(0,0);else setTimeout(()=>document.getElementById(decodeURIComponent(to.hash.slice(1)))?.scrollIntoView(),100);});export default router;
