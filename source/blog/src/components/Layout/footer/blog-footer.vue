<script setup>
import {inject,ref} from 'vue';
import LinSiteStatus from '@/integration/LinSiteStatus.vue';
const site=inject('lin-site',ref({}));
function top(){window.scrollTo({top:0,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});}
</script>
<template><footer class="lin-footer"><div><strong>{{site.title||'林间笔记'}}<span style="color:#aaa98c"> ✦</span></strong><p>一隅天地，几页日常。© {{new Date().getFullYear()}} Lin</p><LinSiteStatus/></div><div><a href="/rss.xml">RSS 订阅 ↗</a><a href="/archives">翻翻旧日子</a><a href="#top" @click.prevent="top">回到顶部 ↑</a></div></footer></template>
