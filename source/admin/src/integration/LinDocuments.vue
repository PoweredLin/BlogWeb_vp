<script setup lang="ts">
import {computed,nextTick,onMounted,ref,watch} from 'vue';
import MarkdownIt from 'markdown-it';
import DOMPurify from 'dompurify';
import {request} from './service';

type DocumentRow={id:string;title:string;category:string;content:string;version:number;created:string;updated:string};
const rows=ref<DocumentRow[]>([]),selected=ref(''),query=ref(''),filter=ref(''),mode=ref<'edit'|'preview'>('edit'),busy=ref(false),notice=ref('');
const draft=ref({title:'',category:'',content:''}),saved=ref({title:'',category:'',content:''}),preview=ref<HTMLElement>();
const dirty=computed(()=>JSON.stringify(draft.value)!==JSON.stringify(saved.value));
const categories=computed(()=>[...new Set(rows.value.map(row=>row.category).filter(Boolean))].sort());
const visibleRows=computed(()=>rows.value.filter(row=>(!filter.value||row.category===filter.value)&&(`${row.title} ${row.category} ${row.content}`.toLocaleLowerCase().includes(query.value.toLocaleLowerCase()))));
const markdown=new MarkdownIt({html:false,linkify:false,breaks:false});
const defaultFence=markdown.renderer.rules.fence!;
markdown.renderer.rules.fence=(tokens,index,options,env,self)=>{
  const token=tokens[index];
  if(token.info.trim().split(/\s+/)[0]==='mermaid')return `<pre class="mermaid-source">${markdown.utils.escapeHtml(token.content)}</pre>`;
  return defaultFence(tokens,index,options,env,self);
};
let renderId=0;

function select(row:DocumentRow){
  if(dirty.value&&!confirm('有未保存的修改，切换文档会丢失这些修改。继续吗？'))return;
  selected.value=row.id;draft.value={title:row.title,category:row.category,content:row.content};saved.value={...draft.value};mode.value='edit';notice.value='';
}
function newDocument(){
  if(dirty.value&&!confirm('有未保存的修改，创建文档会丢失这些修改。继续吗？'))return;
  selected.value='';draft.value={title:'',category:'',content:''};saved.value={...draft.value};mode.value='edit';notice.value='';
}
async function load(keepId=selected.value){rows.value=await request('/api/private/documents');const row=rows.value.find(item=>item.id===keepId);if(row)select(row);else if(!keepId&&rows.value[0])select(rows.value[0]);else if(keepId){selected.value='';draft.value={title:'',category:'',content:''};saved.value={...draft.value};}}
async function save(){
  if(!draft.value.title.trim()){notice.value='请填写文档标题。';return;}
  busy.value=true;notice.value='';
  try{const result=selected.value?await request('/api/private/documents/'+selected.value,'PUT',{...draft.value,version:rows.value.find(row=>row.id===selected.value)?.version}):await request('/api/private/documents','POST',draft.value);selected.value=result.id;draft.value={title:result.title,category:result.category,content:result.content};saved.value={...draft.value};await load(result.id);notice.value='文档已保存。';}
  catch(error){notice.value=error instanceof Error?error.message:'保存失败';}
  finally{busy.value=false;}
}
async function remove(){
  const row=rows.value.find(item=>item.id===selected.value);if(!row||!confirm(`删除「${row.title}」？此操作无法撤销。`))return;
  busy.value=true;try{await request('/api/private/documents/'+row.id,'DELETE',{version:row.version});selected.value='';await load('');notice.value='文档已删除。';}catch(error){notice.value=error instanceof Error?error.message:'删除失败';}finally{busy.value=false;}
}
async function renderPreview(){
  await nextTick();if(!preview.value)return;
  const html=DOMPurify.sanitize(markdown.render(draft.value.content),{USE_PROFILES:{html:true}});
  preview.value.innerHTML=html;
  const sources=[...preview.value.querySelectorAll('pre.mermaid-source')];if(!sources.length)return;
  if(sources.length>8||sources.some(node=>(node.textContent||'').length>12000||/\bclick\b|%%\s*\{|^---/m.test(node.textContent||''))){notice.value='流程图最多 8 段、每段 12,000 字符，不支持点击动作或配置指令。';return;}
  try{
    const mermaid=(await import('mermaid')).default;
    mermaid.initialize({startOnLoad:false,securityLevel:'strict',theme:'neutral',fontFamily:'inherit',maxTextSize:12000,maxEdges:150,flowchart:{htmlLabels:false}});
    for(const source of sources){
      const result=await mermaid.render(`private-doc-flow-${++renderId}`,source.textContent||'');
      const template=document.createElement('template');template.innerHTML=DOMPurify.sanitize(result.svg,{USE_PROFILES:{svg:true,svgFilters:true}});
      source.replaceWith(template.content);
    }
  }catch{notice.value='有一段 Mermaid 流程图无法解析，请检查语法。';}
}
watch([mode,()=>draft.value.content],()=>{if(mode.value==='preview')renderPreview();});
onMounted(()=>load().catch(error=>notice.value=error.message));
</script>

<template>
  <section class="documents-page">
    <header class="documents-heading"><div><span class="space-eyebrow">PRIVATE LIBRARY / NOTES & DIAGRAMS</span><h1>私有文档</h1><p>仅站主可访问的 Markdown 笔记与流程图。</p></div><el-button type="primary" @click="newDocument">新建文档</el-button></header>
    <div class="documents-shell">
      <aside class="documents-sidebar">
        <el-input v-model="query" clearable placeholder="搜索文档" aria-label="搜索文档"/>
        <el-select v-model="filter" clearable placeholder="全部分类" aria-label="按分类筛选"><el-option v-for="item in categories" :key="item" :label="item" :value="item"/></el-select>
        <button v-for="row in visibleRows" :key="row.id" class="document-row" :class="{active:selected===row.id}" @click="select(row)"><strong>{{row.title}}</strong><span>{{row.category||'未分类'}}</span><time>{{new Date(row.updated).toLocaleDateString()}}</time></button>
        <p v-if="!visibleRows.length" class="documents-empty">{{rows.length?'没有匹配的文档。':'还没有文档。'}}</p>
      </aside>
      <main class="document-editor">
        <div class="document-toolbar"><el-radio-group v-model="mode" size="small"><el-radio-button value="edit">编辑</el-radio-button><el-radio-button value="preview">预览</el-radio-button></el-radio-group><span v-if="dirty" class="unsaved">未保存</span><span v-else-if="selected" class="saved-at">已保存 · {{new Date(rows.find(row=>row.id===selected)?.updated||'').toLocaleString()}}</span><span class="toolbar-spacer"/><el-button v-if="selected" type="danger" plain :disabled="busy" @click="remove">删除</el-button><el-button type="primary" :loading="busy" :disabled="!dirty" @click="save">保存</el-button></div>
        <div v-if="mode==='edit'" class="edit-fields"><el-input v-model="draft.title" maxlength="180" placeholder="文档标题" aria-label="文档标题"/><el-input v-model="draft.category" maxlength="80" placeholder="分类（可选）" aria-label="分类"/><el-input v-model="draft.content" type="textarea" :autosize="{minRows:22}" maxlength="200000" show-word-limit placeholder="用 Markdown 记录想法；使用 ```mermaid 代码块绘制流程图。" aria-label="Markdown 文档内容"/></div>
        <article v-else ref="preview" class="document-preview"/>
        <p v-if="notice" class="document-notice" role="status">{{notice}}</p>
      </main>
    </div>
  </section>
</template>

<style scoped>
.documents-page{max-width:1440px;margin:auto}.documents-heading{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;margin-bottom:22px}.documents-heading h1{font-size:28px;margin:9px 0}.documents-heading p,.documents-empty{color:var(--studio-muted);font-size:13px;margin:0}.documents-shell{min-height:640px;display:grid;grid-template-columns:260px minmax(0,1fr);border-top:1px solid var(--studio-line);border-bottom:1px solid var(--studio-line)}.documents-sidebar{padding:16px 14px 16px 0;border-right:1px solid var(--studio-line);display:flex;flex-direction:column;gap:10px}.document-row{border:0;border-left:2px solid transparent;text-align:left;background:transparent;padding:12px 10px;display:grid;gap:5px;cursor:pointer;color:inherit}.document-row:hover,.document-row.active{background:var(--studio-panel);border-left-color:#7c6b9d}.document-row strong{font-size:13px;overflow-wrap:anywhere}.document-row span,.document-row time{font-size:11px;color:var(--studio-muted)}.document-editor{min-width:0;padding:16px 0 22px 22px}.document-toolbar{display:flex;align-items:center;gap:10px;margin-bottom:14px}.toolbar-spacer{flex:1}.saved-at,.unsaved{font-size:11px;color:var(--studio-muted)}.unsaved{color:#b66a3c}.edit-fields{display:grid;grid-template-columns:minmax(200px,1fr) 220px;gap:10px}.edit-fields :deep(.el-textarea){grid-column:1/-1}.edit-fields :deep(textarea){font:13px/1.75 ui-monospace,Consolas,monospace}.document-preview{max-width:860px;min-height:520px;padding:20px 8px;line-height:1.8;overflow-wrap:anywhere}.document-preview :deep(h1),.document-preview :deep(h2),.document-preview :deep(h3){line-height:1.35;margin:1.6em 0 .7em}.document-preview :deep(pre:not(.mermaid-source)){padding:16px;overflow:auto;background:var(--studio-panel);border:1px solid var(--studio-line);border-radius:6px}.document-preview :deep(code){font-family:ui-monospace,Consolas,monospace;font-size:.92em}.document-preview :deep(blockquote){margin:1em 0;padding-left:14px;border-left:3px solid var(--studio-line);color:var(--studio-muted)}.document-preview :deep(img){max-width:100%}.document-preview :deep(table){border-collapse:collapse;max-width:100%;overflow:auto}.document-preview :deep(th),.document-preview :deep(td){border:1px solid var(--studio-line);padding:7px 10px}.document-preview :deep(.mermaid){max-width:100%;height:auto}.document-notice{font-size:12px;color:var(--studio-muted);min-height:1em;margin:8px 0 0}
@media(max-width:760px){.documents-shell{grid-template-columns:1fr}.documents-sidebar{border-right:0;border-bottom:1px solid var(--studio-line);padding-right:0;max-height:270px;overflow:auto}.document-editor{padding:15px 0}.documents-heading{align-items:flex-start}.edit-fields{grid-template-columns:1fr}.edit-fields :deep(.el-textarea){grid-column:auto}.document-toolbar{flex-wrap:wrap}.saved-at{display:none}}
</style>
