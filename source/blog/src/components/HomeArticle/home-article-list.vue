<script setup>
import { nextTick, watch } from "vue";
import { useRouter } from "vue-router";

import { numberFormate } from "@/utils/tool";

import ArticleSkeleton from "./components/article-skeleton.vue";
import Tooltip from "../ToolTip/tooltip.vue";
import Pagination from "../Pagination/pagination.vue";
import GsapCount from "@/components/GsapCount/index";

import { gsapTransY } from "@/utils/transform";
import { isMobile } from "@/utils/tool";

const emit = defineEmits(["pageChange"]);

const props = defineProps({
  articleList: {
    type: Array,
    default: () => {},
  },
  articleTotal: {
    type: Number,
    default: 0,
  },
  param: {
    type: Object,
    default: () => {},
  },
});

const router = useRouter();

/* 文章操作 start */
const operate = (type, item) => {
  switch (type) {
    case "detail":
      router.push({ path: "/article", query: { id: item.id } });
      break;
    case "tag":
      router.push({ path: "/tag" });
      break;
    case "category":
      router.push({ path: "/category" });
      break;
  }
};
/* 文章操作 end */

let layout = " prev, pager, next"; //分页组件会展示的功能项

const pagination = (page) => {
  emit("pageChange", page);
};

watch(
  () => props.articleList,
  () => {
    if (!props.articleList.length) return;
    nextTick(() => {
      let listArticle = [];
      for (let i = 0; i < props.articleList.length; i++) {
        if (!isMobile()) {
          if (i >= 1) {
            listArticle.push(".article" + i);
          }
        } else {
          listArticle.push(".article" + i);
        }
      }
      // Row reveal is handled by CSS, keeping grid geometry stable.
    });
  }
);
</script>

<template><section class="editorial-list"><el-skeleton v-if="param.loading" :rows="8" animated/><template v-else><article v-for="(item,index) in articleList" :key="item.id" :class="['editorial-row','article'+index]"><RouterLink :to="'/blog/'+item.id" class="article-box editorial-link"><figure><img :src="item.article_cover" :alt="item.article_title" loading="lazy"/><span>{{String((param.current-1)*param.size+index+1).padStart(2,'0')}}</span></figure><div class="editorial-copy"><div class="editorial-meta"><span>{{item.category}}</span><time>{{item.createdAt}}</time><b v-if="item.is_top===1">置顶</b></div><h2>{{item.article_title}}</h2><p>{{item.article_description}}</p><div class="editorial-bottom"><span>{{item.tagNameList.slice(0,3).join(' / ')}}</span><b>阅读全文 ↗</b></div></div></RouterLink></article><p v-if="!articleList.length" class="editorial-empty">下一篇随手记，正在路上。</p></template><Pagination v-if="articleTotal>param.size" :layout="layout" :current="param.current" :size="param.size" :total="articleTotal" @pagination="pagination"/></section></template>
<style scoped lang="scss">.editorial-list{width:100%;min-width:0}.editorial-row{border-bottom:1px solid var(--lin-line);padding:27px 0}.editorial-row:first-child{padding-top:0}.editorial-link{display:grid!important;grid-template-columns:265px minmax(0,1fr);gap:30px;color:inherit;min-height:200px}.editorial-link figure{position:relative;margin:0;overflow:hidden;border-radius:4px;height:200px}.editorial-link img{height:100%;width:100%;object-fit:cover;transition:transform .7s}.editorial-link:hover img{transform:scale(1.04)}.editorial-link figure>span{position:absolute;bottom:12px;left:14px;color:white;font:italic 28px Georgia;text-shadow:0 2px 8px #0008}.editorial-copy{min-width:0;display:flex;flex-direction:column;padding:7px 0}.editorial-meta{display:flex;gap:15px;color:var(--lin-muted);align-items:center;font-size:10px}.editorial-meta>span{color:var(--lin-accent);font-size:11px}.editorial-meta>b{font-weight:400;font-size:9px;border:1px solid var(--lin-line);padding:2px 6px}.editorial-copy h2{font-size:25px;line-height:1.5;font-weight:600;letter-spacing:-.5px;margin:16px 0 12px;transition:color .2s}.editorial-link:hover h2{color:var(--lin-accent)}.editorial-copy>p{font-size:13px;line-height:1.95;color:var(--lin-muted);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.editorial-bottom{display:flex;justify-content:space-between;gap:12px;margin-top:auto;padding-top:18px;font-size:10px;color:var(--lin-muted)}.editorial-bottom>b{font-weight:500;color:var(--lin-accent);white-space:nowrap}.editorial-empty{padding:35px;color:var(--lin-muted)}@media(min-width:1400px){.editorial-link{grid-template-columns:300px minmax(0,1fr)}.editorial-link figure{height:210px}}@media(max-width:1050px){.editorial-link{grid-template-columns:210px minmax(0,1fr);gap:22px}.editorial-copy h2{font-size:22px}}@media(max-width:600px){.editorial-link{grid-template-columns:1fr;gap:15px}.editorial-link figure{height:205px}.editorial-copy h2{font-size:23px;margin:12px 0}.editorial-row{padding:25px 0}.editorial-bottom{padding-top:15px}.editorial-copy{padding:0}}</style>
