<script setup lang="ts">
import {ref,onMounted} from 'vue';import {ElMessage} from 'element-plus';import {request} from '@/integration/service';
const status=ref('pending'),rows=ref([]),busy=ref(false);
async function load(){rows.value=await request('/api/admin/comments?status='+status.value);}
async function review(row,state){busy.value=true;try{await request('/api/admin/comments/'+row.id,'PUT',{status:state,version:row.version});ElMessage.success(state==='approved'?'评论已公开':'审核状态已更新');await load();}finally{busy.value=false;}}
onMounted(load);
</script>
<template><el-card><template #header><h2>评论审核</h2></template><el-alert title="所有留言均需你审核通过后公开；已通过的留言也可撤回。" :closable="false" type="info"/><el-radio-group v-model="status" class="my-4" @change="load"><el-radio-button value="pending">待审核</el-radio-button><el-radio-button value="approved">已公开</el-radio-button><el-radio-button value="rejected">已拒绝</el-radio-button></el-radio-group><el-empty v-if="!rows.length" description="当前没有留言"/><article v-for="row in rows" :key="row.id" class="review-item"><strong>{{row.name}}</strong><p class="text-gray-500">{{row.postTitle}} · {{new Date(row.created).toLocaleString()}}</p><p class="content">{{row.content}}</p><el-button v-if="status!=='approved'" type="success" :disabled="busy" @click="review(row,'approved')">审核通过</el-button><el-button v-if="status==='approved'" :disabled="busy" @click="review(row,'pending')">撤回公开</el-button><el-button v-if="status!=='rejected'" type="danger" plain :disabled="busy" @click="review(row,'rejected')">拒绝</el-button></article></el-card></template>
<style scoped>.review-item{padding:22px 0;border-bottom:1px solid var(--el-border-color)}.content{white-space:pre-wrap;overflow-wrap:anywhere;margin:14px 0}</style>
