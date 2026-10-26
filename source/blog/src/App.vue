<script setup>
import { ref, reactive, onMounted, h, provide } from "vue";
import {request} from "@/integration/service";
import "@/integration/blog-v8.scss";
import { isMobile, getWelcomeSay } from "@/utils/tool";
import { addView, getAllPageHeader } from "@/api/config";
import { useRoute, useRouter } from "vue-router";
import { ElNotification } from "element-plus";

import { storeToRefs } from "pinia";
import { user, staticData } from "@/store/index.js";

import BackTop from "@/integration/LinCompass.vue";

const site=ref({});provide('lin-site',site);
const userStore = user();
const router = useRouter();
const route = useRoute();
const { getUserInfo } = storeToRefs(userStore);
const backTopProps = reactive({
  right: "",
  svgWidth: 0,
});
const isPc = ref(true);

const goBack = () => {
  router.go(-1);
};

// 获取所有的网站页面背景图
const getAllPageHeaderBg = async () => {
  const res = await getAllPageHeader();
  if (res.code == 0) {
    staticData().setPageHeaderLIst(res.result);
  } else {
    ElNotification({
      offset: 60,
      title: "错误提示",
      message: h("div", { style: "color: #f56c6c; font-weight: 600;" }, res.message),
    });
  }
};

const welcome = () => {
  // 欢迎
  let msg = getWelcomeSay(getUserInfo.value.nick_name);

  ElNotification({
    offset: 60,
    title: "欢迎～",
    message: h("div", { style: "font-weight: 600;" }, msg),
  });
};

onMounted(async () => {
  try{const s=await request('/api/site');site.value=s;const d=document.documentElement;d.dataset.blogTheme=s.blogTheme||'paper';d.dataset.blogList=s.listStyle||'editorial';d.dataset.blogMotion=String(s.motion!==false);d.dataset.blogSidebar=String(s.showSidebar!==false);d.style.setProperty('--blog-wallpaper',s.blogBackground?'url('+s.blogBackground+')':'none');}catch{}
  // 首次判断是手机还是pc
  backTopProps.right = 0;
  backTopProps.svgWidth = 6;
  isPc.value = !isMobile();

  // 上传访问量
  await addView();
  if (true) {
    // 获取背景图片
    getAllPageHeaderBg();
    if(getUserInfo.value.id) welcome();
  }
});
</script>

<template>
  <div class="app">
    <router-view></router-view>
    <BackTop
      v-if="route.path !== '/'"
      :right="backTopProps.right"
      :svgWidth="backTopProps.svgWidth"
      :rotateDeg="-42"
    />
    <i
      v-if="!isPc && ['home', '/'].includes(route.path)"
      class="iconfont icon-fanhui"
      @click="goBack"
    ></i>


  </div>
</template>

<style lang="scss">
.app {
  width: 100%;
  box-sizing: border-box;
}

.icon-fanhui {
  position: fixed;
  left: 5px;
  top: 60px;
  font-size: 2.2rem;
  color: var(--font-color);
  z-index: 999;
}
</style>
