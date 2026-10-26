<script setup lang="ts" name="Login">
import Motion from "./utils/motion";
import { useRouter, useRoute } from "vue-router";
import { message } from "@/utils/message";
import { loginRules } from "./utils/rule";
import { useNav } from "@/layout/hooks/useNav";
import type { FormInstance } from "element-plus";
import { useUserStoreHook } from "@/store/modules/user";
import { useLayout } from "@/layout/hooks/useLayout";
import { bg, avatar, illustration } from "./utils/static";
import { useRenderIcon } from "@/components/ReIcon/src/hooks";
import { ref, reactive, toRaw, onMounted, onBeforeUnmount } from "vue";
import { useDataThemeChange } from "@/layout/hooks/useDataThemeChange";
import { storageLocal } from "@pureadmin/utils";

import dayIcon from "@/assets/svg/day.svg?component";
import darkIcon from "@/assets/svg/dark.svg?component";
import Lock from "@iconify-icons/ri/lock-fill";
import User from "@iconify-icons/ri/user-3-fill";



type RuleFormType = {
  username?: string;
  password?: string;
};

const router = useRouter();const route=useRoute();
const loading = ref(false);
const ruleFormRef = ref<FormInstance>();

const { initStorage } = useLayout();
initStorage();

const { dataTheme, dataThemeChange } = useDataThemeChange();
dataThemeChange();

const { title } = useNav();

const ruleForm = reactive<RuleFormType>({
  username: "",
  password: ""
});

const isRememberMe = ref(false);

const onLogin=async(formEl)=>{if(!formEl)return;loading.value=true;try{await formEl.validate();await useUserStoreHook().loginByUsername(ruleForm);const next=String(route.query.next||'');if(useUserStoreHook().role===1&&/^\/workspace(?:\/[a-z]+)?$/.test(next)){location.href=next;}else router.push('/home');message('登录成功',{type:'success'});}catch(e){message(e.message||'请检查账号和密码',{type:'error'});}finally{loading.value=false;}};
/** 使用公共函数，避免`removeEventListener`失效 */
function onkeypress({ code }: KeyboardEvent) {
  if (code === "Enter") {
    onLogin(ruleFormRef.value);
  }
}

const goRegister = () => {
  router.push("/register");
};

const changeAccount = () => {
  ruleForm.password = "";
};

onMounted(()=>{window.document.addEventListener('keypress',onkeypress);ruleForm.username='admin';storageLocal().removeItem('loginInfo');});

onBeforeUnmount(() => {
  window.document.removeEventListener("keypress", onkeypress);
});
</script>

<template>
  <div class="select-none relative">
    <img :src="bg" class="wave" />
    <div class="flex-c absolute right-5 top-3">
      <!-- 主题 -->
      <el-switch
        v-model="dataTheme"
        inline-prompt
        :active-icon="dayIcon"
        :inactive-icon="darkIcon"
        @change="dataThemeChange"
      />
    </div>
    <div class="login-container">
      <div class="img">
        <component :is="toRaw(illustration)" />
      </div>
      <div class="login-box">
        <div class="login-form">
          <avatar class="avatar" />
          <Motion>
            <h2 class="outline-none">{{ title }}</h2>
          </Motion>

          <el-form
            ref="ruleFormRef"
            :model="ruleForm"
            :rules="loginRules"
            size="large"
          >
            <Motion :delay="100">
              <el-form-item
                :rules="[
                  {
                    required: true,
                    message: '请输入账号',
                    trigger: 'blur'
                  }
                ]"
                prop="username"
              >
                <el-input
                  clearable
                  v-model="ruleForm.username"
                  placeholder="账号"
                  @clear="changeAccount"
                  :prefix-icon="useRenderIcon(User)"
                />
              </el-form-item>
            </Motion>

            <Motion :delay="150">
              <el-form-item prop="password">
                <el-input
                  clearable
                  show-password
                  v-model="ruleForm.password"
                  placeholder="密码"
                  :prefix-icon="useRenderIcon(Lock)"
                />
              </el-form-item>
            </Motion>

            <Motion :delay="250">
              <el-button
                class="w-full mt-4"
                size="default"
                type="primary"
                :loading="loading"
                @click="onLogin(ruleFormRef)"
              >
                登录
              </el-button>
            </Motion>
            <Motion :delay="250" class="register"><a href="/">返回博客</a><span>仅站主与受邀作者</span></Motion>
          </el-form>
        </div>
      </div>
    </div>

  </div>
</template>

<style scoped>
@import url("@/style/login.css");
</style>

<style lang="scss" scoped>
:deep(.el-input-group__append, .el-input-group__prepend) {
  padding: 0;
}

.register {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.8em;
  color: #676767;

  :deep(.el-checkbox.el-checkbox--large .el-checkbox__label) {
    font-size: 0.8em;
    color: #676767;
  }
}
.line {
  cursor: pointer;
  text-decoration: underline;
}

.filings {
  position: absolute;
  bottom: 5px;
  left: 50%;
  transform: translateX(-50%);
  text-align: center;
  color: #333;
  font-size: 12px;

  .change-color {
    text-decoration: none;
    transition: all 0.3s;

    &:hover {
      color: #000;
    }
  }
}
</style>
