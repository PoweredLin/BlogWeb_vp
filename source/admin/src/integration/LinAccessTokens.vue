<script setup lang="ts">
import {onMounted, ref} from 'vue';
import {request} from './service';

type TokenRow={id:string;prefix:string;name:string;scopes:string[];expires:number;created:string;lastUsed:number};
const rows=ref<TokenRow[]>([]),name=ref(''),days=ref(90),scopes=ref(['content:draft:write']),busy=ref(false),notice=ref(''),issued=ref('');
const options=[['content:draft:write','创建文章草稿'],['content:publish','发布文章'],['content:import','JSON 批量导入'],['automation:submit','提交本地 AI 自动化结果']];
async function load(){rows.value=await request('/api/private/access-tokens');}
async function create(){busy.value=true;notice.value='';try{const result=await request('/api/private/access-tokens','POST',{name:name.value,scopes:scopes.value,expiresInDays:days.value});issued.value=result.token;name.value='';await load();}catch(error){notice.value=error.message;}finally{busy.value=false;}}
async function revoke(row:TokenRow){if(!confirm(`撤销「${row.name}」？使用它的 AI 工具将立即无法访问。`))return;await request('/api/private/access-tokens/'+row.id,'DELETE');await load();}
async function copy(){await navigator.clipboard.writeText(issued.value);notice.value='令牌已复制';}
onMounted(()=>load().catch(error=>notice.value=error.message));
</script>

<template>
  <section class="access-page">
    <header><div><span class="space-eyebrow">AI / API ACCESS</span><h1>Access Token</h1><p>为每个本地 AI 工具单独授权。令牌创建后只显示一次。</p></div></header>
    <form class="token-create" @submit.prevent="create">
      <label>令牌名称<el-input v-model="name" maxlength="100" placeholder="例如：本地写作助手" required/></label>
      <label>有效期（天）<el-input-number v-model="days" :min="1" :max="365"/></label>
      <fieldset><legend>允许的操作</legend><el-checkbox-group v-model="scopes"><el-checkbox v-for="[value,label] in options" :key="value" :value="value">{{label}}</el-checkbox></el-checkbox-group></fieldset>
      <el-button type="primary" native-type="submit" :loading="busy" :disabled="!name.trim()||!scopes.length">创建令牌</el-button>
      <p v-if="notice" role="status">{{notice}}</p>
    </form>
    <section v-if="issued" class="issued-token" aria-label="新建令牌">
      <strong>请立即复制，离开此页后无法再次查看。</strong>
      <el-input :model-value="issued" readonly aria-label="新建 Access Token"/>
      <el-button @click="copy">复制令牌</el-button>
    </section>
    <section class="token-list" aria-label="现有令牌">
      <h2>现有令牌</h2>
      <p v-if="!rows.length" class="empty">还没有创建 Access Token。</p>
      <article v-for="row in rows" :key="row.id">
        <div><strong>{{row.name}}</strong><code>{{row.prefix}}…</code><small>权限：{{row.scopes.join('、')}}</small><small>到期：{{new Date(row.expires).toLocaleString()}}</small></div>
        <el-button type="danger" plain @click="revoke(row)">撤销</el-button>
      </article>
    </section>
    <aside class="api-note"><strong>文章 API</strong><code>POST /api/v1/posts</code><span>默认创建草稿；发布需同时授予“发布文章”权限，并在请求中指定 <code>requestedState: "published"</code>。</span><strong>JSON 导入</strong><code>POST /api/v1/imports/validate</code><code>POST /api/v1/imports</code></aside>
  </section>
</template>

<style scoped>
.access-page{max-width:980px;margin:auto}.access-page header h1{font-size:30px;margin:12px 0}.access-page header p,.empty{font-size:13px;color:var(--studio-muted)}.token-create,.token-list,.api-note,.issued-token{margin-top:24px;padding:22px 0;border-top:1px solid var(--studio-line)}.token-create{display:grid;grid-template-columns:minmax(220px,1fr) 180px;gap:18px;align-items:end}.token-create>label{display:grid;gap:8px;font-size:12px}.token-create fieldset{grid-column:1/-1;border:0;padding:0;margin:0}.token-create legend{font-size:12px;margin-bottom:8px}.token-create fieldset :deep(.el-checkbox-group){display:flex;flex-wrap:wrap;gap:8px 20px}.token-create>button{justify-self:start}.token-create>p{margin:0;font-size:12px}.token-list h2{font-size:18px}.token-list article{display:flex;justify-content:space-between;align-items:center;gap:16px;border-bottom:1px solid var(--studio-line);padding:16px 0}.token-list article>div{display:grid;grid-template-columns:auto 1fr;gap:6px 12px;min-width:0}.token-list small{grid-column:1/-1;color:var(--studio-muted);font-size:11px}.token-list code,.api-note code{font-family:ui-monospace,Consolas,monospace;font-size:11px}.issued-token{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.issued-token strong{width:100%;font-size:13px}.issued-token :deep(.el-input){max-width:620px}.api-note{display:grid;grid-template-columns:170px 1fr;gap:10px;font-size:12px;align-items:start}.api-note span{grid-column:2;line-height:1.7}@media(max-width:600px){.token-create{grid-template-columns:1fr}.token-create fieldset{grid-column:auto}.api-note{grid-template-columns:1fr}.api-note span{grid-column:auto}.token-list article{align-items:flex-start}.token-list article>div{overflow-wrap:anywhere}}
</style>
