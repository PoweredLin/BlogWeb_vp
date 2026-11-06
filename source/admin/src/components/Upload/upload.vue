<script lang="ts" setup>
import { watch, ref, nextTick } from "vue";
import { Delete, Plus, ZoomIn, Loading } from "@element-plus/icons-vue";

const emit = defineEmits(["update:fileList", "handleRemove"]);
const props = defineProps({
  fileList: {
    type: Array,
    default: () => []
  },
  limit: {
    type: Number,
    default: 1
  },
  preview: {
    type: Boolean,
    default: false
  },
  multiple: {
    type: Boolean,
    default: false
  },
  width: {
    type: Number,
    default: 200
  },
  height: {
    type: Number,
    default: 200
  }
});

const dialogVisible = ref(false);
const previewIndex = ref(0);
const uploadFileList = ref([]);
const showUpload = ref(true);
const previewAttempts = ref<Record<string, number>>({});
const retryPreview = file => {
  const key = String(file.uid ?? file.url);
  previewAttempts.value[key] = (previewAttempts.value[key] || 0) + 1;
};

const uploadChange = () => {
  nextTick(() => {
    if (uploadFileList.value.length >= props.limit) {
      showUpload.value = false;
    }
    emit("update:fileList", uploadFileList.value); // 修改父组件的文件值
  });
};
function handlePictureCardPreview(file: any) {
  // 图片预览
  const index = uploadFileList.value.findIndex(v => v.uid == file.uid);
  previewIndex.value = index;
  dialogVisible.value = true;
}

function closeImgViewer() {
  previewIndex.value = 0;
  dialogVisible.value = false;
}

const handleRemove = async file => {
  if (file) {
    const { url } = file;
    const index = uploadFileList.value.findIndex(file => file.url == url);

    if (index != -1) {
      uploadFileList.value.splice(index, 1);
    }
    showUpload.value = true;
    emit("update:fileList", uploadFileList.value); // 修改父组件的文件值
  }
};

watch(
  () => props.fileList,
  newVal => {
    uploadFileList.value = newVal;
    if (newVal.length >= props.limit) {
      showUpload.value = false;
    }
    if (!newVal.length) {
      showUpload.value = true;
    }
  },
  {
    immediate: true,
    deep: true
  }
);
</script>

<template>
  <el-upload
    ref="uploadAvatarRef"
    v-model:file-list="uploadFileList"
    :class="[showUpload && !preview ? '' : 'hide-upload']"
    action="#"
    list-type="picture-card"
    :auto-upload="false"
    :multiple="multiple"
    :limit="limit"
    :on-change="uploadChange"
  >
    <el-icon><Plus /></el-icon>
    <template #file="{ file }">
      <div class="cover-item">
        <el-image
          :key="String(file.uid ?? file.url) + ':' + (previewAttempts[String(file.uid ?? file.url)] || 0)"
          :style="{ width: width + 'px', height: height + 'px' }"
          fit="cover"
          :src="file.url"
          :alt="file.name || '文章封面'"
        >
          <template #placeholder>
            <div class="cover-feedback" role="status" aria-live="polite">
              <el-icon class="cover-spinner"><Loading /></el-icon>
              <span>正在加载预览…</span>
            </div>
          </template>
          <template #error>
            <div class="cover-feedback cover-error" role="alert">
              <span>预览加载失败</span>
              <button type="button" @click.stop="retryPreview(file)">重新加载</button>
              <small>仍失败时请重新选择 PNG、JPEG 或 WebP 图片</small>
            </div>
          </template>
        </el-image>
        <button
          v-if="!preview"
          class="cover-delete"
          type="button"
          aria-label="移除封面"
          title="移除图片"
          @click.stop="handleRemove(file)"
        >
          <el-icon><Delete /></el-icon>
        </button>
        <button
          class="cover-preview"
          type="button"
          aria-label="预览封面"
          title="放大预览"
          @click.stop="handlePictureCardPreview(file)"
        >
          <el-icon><zoom-in /></el-icon>
        </button>
      </div>
    </template>
  </el-upload>
  <el-image-viewer
    v-if="dialogVisible"
    :url-list="uploadFileList.map(v => v.url)"
    :initial-index="previewIndex"
    :teleported="true"
    @close="closeImgViewer"
  />
</template>

<style lang="scss" scoped>
.hide-upload {
  :deep(.el-upload--picture-card) {
    display: none;
  }
}

.el-upload-list--picture-card {
  display: flex;
}

.cover-feedback {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 9px;
  height: 100%;
  padding: 12px;
  font-size: 12px;
  text-align: center;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-light);
}
.cover-spinner { animation: cover-spin 1s linear infinite; font-size: 22px; }
.cover-item { position: relative; width: 100%; height: 100%; }
.cover-delete {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 3;
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: 1px solid #ffffff80;
  border-radius: 50%;
  color: #fff;
  background: #1e293bcc;
  cursor: pointer;
}
.cover-preview {
  position: absolute;
  right: 8px;
  bottom: 8px;
  z-index: 3;
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: 1px solid #ffffff80;
  border-radius: 50%;
  color: #fff;
  background: #1e293bcc;
  cursor: pointer;
}
.cover-preview:hover { background: #111827; }
.cover-delete:hover { background: #111827; }
.cover-delete:focus-visible, .cover-preview:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 2px; }
.cover-error button {
  position: relative;
  z-index: 2;
  padding: 4px 10px;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  cursor: pointer;
  color: var(--el-color-primary);
  background: var(--el-bg-color);
}
@keyframes cover-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .cover-spinner { animation: none; } }
</style>
