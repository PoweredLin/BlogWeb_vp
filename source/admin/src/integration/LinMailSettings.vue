<script setup lang="ts">
import {onMounted, ref} from 'vue';
import {request} from './service';

type Settings={reportSources:string[];host:string;port:number;sender:string;recipient:string;username:string;passwordConfigured:boolean;useTls:boolean;timezone:string;enabled:boolean;weekday:number;sendTime:string};
type Run={id:string;kind:string;status:string;recipient:string;created:string;finished:string|null;error:string};
const form=ref<Settings>({reportSources:['posts'],host:'',port:587,sender:'',recipient:'',username:'',passwordConfigured:false,useTls:true,timezone:'Asia/Shanghai',enabled:false,weekday:1,sendTime:'09:00'});
const password=ref(''),testRecipient=ref(''),runs=ref<Run[]>([]),preview=ref<any>(null),busy=ref(''),notice=ref('');
const days=['周一','周二','周三','周四','周五','周六','周日'];
async function load(){const [config,history]=await Promise.all([request('/api/private/mail/settings'),request('/api/private/mail/runs')]);form.value={...form.value,...config};runs.value=history;}
async function save(){busy.value='save';notice.value='';try{const body:any={...form.value};if(password.value)body.password=password.value;delete body.passwordConfigured;form.value={...form.value,...await request('/api/private/mail/settings','PUT',body)};password.value='';notice.value='设置已保存。'}finally{busy.value='';}}
async function changeEnabled(value:boolean){try{await save();}catch(error){form.value.enabled=!value;notice.value=error.message;}}
async function test(){busy.value='test';notice.value='';try{await save();await request('/api/private/mail/test','POST',{recipient:testRecipient.value||undefined});notice.value='测试邮件已发送，请检查收件箱和垃圾邮件。';}catch(error){notice.value=error instanceof Error?error.message:'邮件测试失败';}finally{busy.value='';}}
async function loadPreview(){busy.value='preview';try{preview.value=await request('/api/private/mail/preview');}finally{busy.value='';}}
async function send(){busy.value='send';try{const result=await request('/api/private/mail/send','POST');notice.value=result.status==='succeeded'?'周报已发送。':'邮件发送失败，请查看投递记录。';await load();}finally{busy.value='';}}
async function retry(run:Run){busy.value=run.id;try{await request(`/api/private/mail/runs/${run.id}/retry`,'POST',{});await load();}finally{busy.value='';}}
onMounted(()=>load().catch(error=>notice.value=error.message));
</script>

<template>
  <section class="mail-page">
    <header class="mail-heading"><div><span class="space-eyebrow">DELIVERY / WEEKLY DIGEST</span><h1>邮件推送</h1><p>配置发件账户，预览并发送个人空间周报。</p></div><el-switch v-model="form.enabled" active-text="自动发送已开启" inactive-text="自动发送已暂停" @change="changeEnabled"/></header>
    <form class="mail-form" @submit.prevent="save">
      <label>SMTP 服务器<el-input v-model="form.host" placeholder="smtp.example.com" autocomplete="off" required/></label>
      <label>端口<el-input-number v-model="form.port" :min="1" :max="65535"/><small class="mail-hint">587 通常配合 STARTTLS；465 通常配合隐式 TLS。端口由邮箱服务商决定。</small></label>
      <label>发件邮箱<el-input v-model="form.sender" type="email" autocomplete="email" required/></label>
      <label>默认收件邮箱<el-input v-model="form.recipient" type="email" autocomplete="email" required/></label>
      <label>SMTP 用户名<el-input v-model="form.username" autocomplete="username" required/></label>
      <label>应用授权码<el-input v-model="password" type="password" show-password autocomplete="new-password" :placeholder="form.passwordConfigured?'已配置；留空保持不变':'填写邮箱服务商提供的授权码'"/></label>
      <label>时区<el-input v-model="form.timezone" placeholder="Asia/Shanghai" required/></label>
      <label class="mail-tls">连接加密<el-select v-model="form.useTls"><el-option label="STARTTLS（通常端口 587）" :value="true"/><el-option label="隐式 TLS（通常端口 465）" :value="false"/></el-select></label>
      <fieldset><legend>每周发送计划</legend><el-select v-model="form.weekday"><el-option v-for="(day,index) in days" :key="day" :label="day" :value="index"/></el-select><el-time-picker v-model="form.sendTime" format="HH:mm" value-format="HH:mm"/></fieldset>
      <fieldset><legend>周报内容（私人内容仅发送到你配置的邮箱）</legend><el-checkbox-group v-model="form.reportSources"><el-checkbox value="posts">已发布文章</el-checkbox><el-checkbox value="notes">私人日志</el-checkbox><el-checkbox value="tasks">任务概览</el-checkbox><el-checkbox value="automation">自动化运行</el-checkbox></el-checkbox-group></fieldset><div class="mail-actions"><el-button type="primary" native-type="submit" :loading="busy==='save'">保存设置</el-button><el-input v-model="testRecipient" type="email" placeholder="测试收件箱（可选）"/><el-button :loading="busy==='test'" @click="test">发送测试邮件</el-button></div>
    </form>
    <p v-if="notice" class="mail-notice" role="status">{{notice}}</p>
    <section class="mail-preview">
      <header><div><h2>周报预览</h2><p>按已保存的内容范围汇总。发送前先检查预览。</p></div><el-button :loading="busy==='preview'" @click="loadPreview">刷新预览</el-button></header>
      <div v-if="preview" class="preview-paper"><strong>{{preview.subject}}</strong><small>{{preview.period.from}} 至 {{preview.period.to}}</small><p>本周发布 {{preview.posts.length}} 篇文章</p><ul><li v-for="post in preview.posts" :key="post.slug">{{post.title}}</li></ul><pre style="white-space:pre-wrap;font:12px/1.8 inherit">{{preview.text}}</pre><el-button type="primary" :loading="busy==='send'" @click="send">立即发送</el-button></div>
      <el-empty v-else description="点击刷新预览" :image-size="64"/>
    </section>
      <section class="mail-history"><h2>最近投递</h2><el-empty v-if="!runs.length" description="暂无投递记录" :image-size="55"/><article v-for="run in runs" :key="run.id"><div><strong>{{run.kind==='scheduled'?'定时发送':run.kind==='retry'?'手动重试':'手动发送'}}</strong><small>{{run.recipient}} · {{new Date(run.created).toLocaleString()}}</small><small v-if="run.error" class="mail-error">{{run.status==='unknown'?'投递结果未知，请先检查收件箱。':'失败原因：'+run.error}}</small></div><el-tag :type="run.status==='succeeded'?'success':run.status==='failed'?'danger':'info'">{{run.status==='succeeded'?'已发送':run.status==='failed'?'失败':run.status==='unknown'?'结果未知':run.status}}</el-tag><el-button v-if="run.status==='failed'" size="small" :loading="busy===run.id" @click="retry(run)">重试</el-button></article></section>
  </section>
</template>

<style scoped>
.mail-page{max-width:1000px;margin:auto}.mail-heading{display:flex;justify-content:space-between;align-items:center;gap:24px}.mail-heading h1{font-size:28px;margin:12px 0}.mail-heading p,.mail-preview header p{font-size:13px;color:var(--studio-muted)}.mail-form,.mail-preview,.mail-history{margin-top:25px;padding-top:22px;border-top:1px solid var(--studio-line)}.mail-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.mail-form>label{display:grid;gap:8px;font-size:12px}.mail-tls{align-content:end}.mail-hint{font-size:11px;line-height:1.5;color:var(--studio-muted)}.mail-form fieldset{grid-column:1/-1;border:0;padding:0;margin:0;display:flex;align-items:center;gap:12px}.mail-form legend{font-size:12px;margin-bottom:9px}.mail-actions{grid-column:1/-1;display:flex;gap:10px;align-items:center;flex-wrap:wrap}.mail-actions .el-input{max-width:260px}.mail-notice{font-size:12px;color:var(--studio-muted);overflow-wrap:anywhere}.mail-preview>header{display:flex;justify-content:space-between;align-items:center}.mail-preview h2,.mail-history h2{font-size:18px}.preview-paper{margin-top:14px;border:1px solid var(--studio-line);padding:20px;max-width:650px}.preview-paper strong,.preview-paper small{display:block}.preview-paper small,.mail-history small{font-size:11px;color:var(--studio-muted);margin-top:7px}.preview-paper li{font-size:13px;line-height:1.9}.mail-history article{display:flex;align-items:center;gap:12px;padding:14px 0;border-bottom:1px solid var(--studio-line)}.mail-history article>div{display:grid;min-width:0;margin-right:auto}.mail-history strong{font-size:13px}.mail-history small{overflow-wrap:anywhere}.mail-error{color:#b5473c!important}@media(max-width:600px){.mail-heading{align-items:flex-start;flex-direction:column}.mail-form{grid-template-columns:1fr}.mail-form fieldset,.mail-actions{grid-column:auto}.mail-actions>*{max-width:100%}.mail-history article{align-items:flex-start;flex-wrap:wrap}}
</style>
