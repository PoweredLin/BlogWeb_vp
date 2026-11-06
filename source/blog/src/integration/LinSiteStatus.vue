<script setup>
import {onMounted,onBeforeUnmount} from 'vue';
import {retainStatus,serviceLabel,serviceState,runtimeLabel,siteSince} from './site-status';
defineProps({compact:Boolean});
let release;onMounted(()=>{release=retainStatus();});onBeforeUnmount(()=>release?.());
</script>
<template><div class="site-status" :class="{'is-compact':compact}"><span v-if="!compact" class="service-check" :data-state="serviceState" role="status"><i/>{{serviceLabel}}</span><span class="site-runtime" :title="siteSince?'建站日期：'+siteSince:'在博客设置中填写建站日期'">{{siteSince?'已相伴 '+runtimeLabel:runtimeLabel}}</span></div></template>
<style scoped>.site-status{display:flex;flex-wrap:wrap;gap:8px 18px;font-size:11px;color:var(--lin-muted);line-height:1.8;font-variant-numeric:tabular-nums}.service-check{display:inline-flex;align-items:center;gap:7px}.service-check i{width:6px;height:6px;border-radius:50%;background:#b3a17a}.service-check[data-state=online] i{background:#6d967b;box-shadow:0 0 0 3px #6d967b15}.is-compact{justify-content:center;margin:8px 0 16px}.site-runtime{overflow-wrap:anywhere}</style>
