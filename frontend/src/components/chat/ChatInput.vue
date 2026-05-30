<script setup lang="ts">
import { ref } from 'vue'
import { UploadFilled } from '@element-plus/icons-vue'
import type { UploadFile } from 'element-plus'

const emit = defineEmits<{
  send: [text: string]
  upload: [files: File[]]
}>()

const text = ref('')
const uploading = ref(false)

function handleSend() {
  const msg = text.value.trim()
  if (!msg) return
  emit('send', msg)
  text.value = ''
}

function handleUpload(file: UploadFile) {
  if (file.raw) {
    emit('upload', [file.raw])
  }
  return false
}
</script>

<template>
  <div class="chat-input">
    <div class="input-row">
      <el-upload
        :show-file-list="false"
        :auto-upload="false"
        :on-change="handleUpload as any"
        accept="*"
        multiple
      >
        <el-button :icon="UploadFilled" circle />
      </el-upload>
      <el-input
        v-model="text"
        placeholder="输入消息..."
        :rows="2"
        type="textarea"
        @keydown.enter.exact.prevent="handleSend"
      />
      <el-button type="primary" :disabled="!text.trim()" @click="handleSend">
        发送
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.chat-input {
  border-top: 1px solid #e4e7ed;
  padding: 16px 24px;
  background: #fff;
}
.input-row {
  display: flex;
  align-items: flex-end;
  gap: 10px;
}
.input-row :deep(.el-textarea) {
  flex: 1;
}
</style>
