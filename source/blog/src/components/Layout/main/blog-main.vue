<template>
  <div class="main_box">
    <router-view v-slot="{ Component }">
      <keep-alive>
        <component :is="Component" v-if="$route.meta.keepAlive" :key="$route.fullPath.split('#')[0]"></component>
      </keep-alive>
      <component :is="Component" v-if="!$route.meta.keepAlive" :key="$route.fullPath.split('#')[0]"></component>
    </router-view>
  </div>
</template>
