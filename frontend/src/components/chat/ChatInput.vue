<script setup lang="ts">
import { ref } from 'vue'
import { UploadFilled, Promotion } from '@element-plus/icons-vue'
import type { UploadFile } from 'element-plus'

const emit = defineEmits<{
  send: [text: string]
  upload: [files: File[]]
}>()

const text = ref('')

function handleSend() {
  const msg = text.value.trim()
  if (!msg) return
  emit('send', msg)
  text.value = ''
}

const fileBatch: File[] = []
let batchTimer: ReturnType<typeof setTimeout> | null = null

function handleUpload(file: UploadFile) {
  if (file.raw) {
    fileBatch.push(file.raw)
    if (batchTimer) clearTimeout(batchTimer)
    batchTimer = setTimeout(() => {
      emit('upload', [...fileBatch])
      fileBatch.length = 0
      batchTimer = null
    }, 100)
  }
  return false
}
</script>

<template>
  <div class="chat-input">
    <div class="input-row">
      <div class="input-left">
        <el-upload
          :show-file-list="false"
          :auto-upload="false"
          :on-change="handleUpload as any"
          accept="*"
          multiple
        >
          <el-button :icon="UploadFilled" size="large" circle class="upload-btn" />
        </el-upload>
      </div>
      <el-input
        v-model="text"
        placeholder="输入消息，Enter 发送..."
        :rows="2"
        type="textarea"
        resize="none"
        @keydown.enter.exact.prevent="handleSend"
      />
      <el-button
        type="primary"
        size="large"
        :icon="Promotion"
        :disabled="!text.trim()"
        @click="handleSend"
      >
        发送
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.chat-input {
  border-top: 1px solid #e8eaed;
  padding: 16px 24px;
  background: #fafbfc;
}
.input-row {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  max-width: 800px;
  margin: 0 auto;
}
.input-left {
  display: flex;
  align-items: center;
}
.upload-btn {
  color: #606266;
}
.input-row :deep(.el-textarea__inner) {
  font-size: 15px;
  border-radius: 12px;
  padding: 10px 16px;
  background: #fff;
}
.input-row :deep(.el-textarea) {
  flex: 1;
}
</style>
