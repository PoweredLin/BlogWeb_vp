<template>
  <div class="card-title">
    <LinIcon :name="({公告:'chat',标签:'spark',网站资讯:'grid',交流:'heart',目录:'book',推荐文章:'book'})[props.title]||'spark'" :size="17" class="inline-icon"/>
    <span> {{ props.title }}</span>
  </div>
  <slot></slot>
</template>
<script setup>
import LinIcon from "@/integration/LinIcon.vue";
const props = defineProps({
  icon: {
    type: String,
    default: "-",
  },
  title: {
    type: String,
    default: "-",
  },
  size: {
    type: String,
    default: "1.2rem",
  },
  color: {
    type: String,
    default: "#676767",
  },
});
</script>
<style lang="scss" scoped>
.card-title {
  font-size: 1.2rem;
  line-height: 2.4;
  .iconfont {
    font-weight: 900;
  }
  span {
    margin-left: 0.3rem;
  }
}
</style>
