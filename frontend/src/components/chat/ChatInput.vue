<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { UploadFilled, Promotion } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { UploadFile } from 'element-plus'
import api from '../../api/client'

const emit = defineEmits<{
  send: [text: string]
  upload: [files: File[]]
}>()

const text = ref('')
const webSearchEnabled = ref(true)
const ragMode = ref<'user' | 'conversation'>('user')
const dragOver = ref(false)

onMounted(async () => {
  try {
    const { data } = await api.get('/user/settings')
    if (data.code === 0) {
      webSearchEnabled.value = data.data.web_search_enabled ?? true
      ragMode.value = data.data.rag_mode ?? 'user'
    }
  } catch {
    // settings API not yet available, use defaults
  }
})

async function saveSettings() {
  try {
    await api.put('/user/settings', {
      web_search_enabled: webSearchEnabled.value,
      rag_mode: ragMode.value,
    })
  } catch {
    // API not yet available, ignore
  }
}

async function onWebSearchChange(val: boolean) {
  webSearchEnabled.value = val
  await saveSettings()
}

async function onRagModeChange(val: 'user' | 'conversation') {
  ragMode.value = val
  await saveSettings()
}

function handleSend() {
  const msg = text.value.trim()
  if (!msg) return
  emit('send', msg)
  text.value = ''
}

const fileBatch: File[] = []
let batchTimer: ReturnType<typeof setTimeout> | null = null
const MAX_FILES = 10

function handleUpload(file: UploadFile) {
  if (file.raw) {
    if (fileBatch.length >= MAX_FILES) {
      ElMessage.warning(`最多上传 ${MAX_FILES} 个文件`)
      return false
    }
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

// Drag-and-drop
function onDragOver(e: DragEvent) {
  e.preventDefault()
  dragOver.value = true
}
function onDragLeave() {
  dragOver.value = false
}
function onDrop(e: DragEvent) {
  e.preventDefault()
  dragOver.value = false
  const files = e.dataTransfer?.files
  if (files && files.length > 0) {
    if (files.length > MAX_FILES) {
      ElMessage.warning(`最多上传 ${MAX_FILES} 个文件，当前选择了 ${files.length} 个`)
    }
    emit('upload', Array.from(files).slice(0, MAX_FILES))
  }
}
</script>

<template>
  <div
    class="chat-input"
    :class="{ 'drag-over': dragOver }"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
  >
    <div class="input-toolbar">
      <el-upload
        :show-file-list="false"
        :auto-upload="false"
        :on-change="handleUpload as any"
        :limit="MAX_FILES"
        accept="*"
        multiple
      >
        <el-button :icon="UploadFilled" class="upload-btn">上传</el-button>
      </el-upload>
      <div class="toolbar-right">
        <el-switch
          v-model="webSearchEnabled"
          size="small"
          active-text="网络搜索"
          @change="onWebSearchChange"
        />
        <el-radio-group
          v-model="ragMode"
          size="small"
          @change="onRagModeChange"
        >
          <el-radio-button value="user">全局知识库</el-radio-button>
          <el-radio-button value="conversation">会话知识库</el-radio-button>
        </el-radio-group>
      </div>
    </div>
    <div class="input-row">
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
        :icon="Promotion"
        :disabled="!text.trim()"
        @click="handleSend"
        class="send-btn"
      >
        发送
      </el-button>
    </div>
    <div class="drag-hint" v-if="dragOver">释放文件以添加</div>
  </div>
</template>

<style scoped>
.chat-input {
  border-top: 1px solid #e8eaed;
  padding: 12px 24px 16px;
  background: #fafbfc;
  position: relative;
  transition: border-color .2s, background .2s;
}
.chat-input.drag-over {
  border-color: #409eff;
  background: #ecf5ff;
}
.input-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 10px;
  max-width: 800px;
  margin-left: auto;
  margin-right: auto;
}
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 16px;
}
.input-row {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  max-width: 800px;
  margin: 0 auto;
}
.upload-btn {
  flex-shrink: 0;
  height: 34px;
  border-radius: 8px;
  padding: 0 18px;
  font-size: 14px;
}
.send-btn {
  flex-shrink: 0;
  height: 40px;
  border-radius: 10px;
  padding: 0 22px;
  font-size: 15px;
}
.input-row :deep(.el-textarea__inner) {
  font-size: 15px;
  border-radius: 12px;
  padding: 10px 16px;
  background: #fff;
  min-height: 40px;
}
.input-row :deep(.el-textarea) {
  flex: 1;
}
.drag-hint {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  color: #409eff;
  font-weight: 600;
  background: rgba(236, 245, 255, 0.9);
  pointer-events: none;
  border-radius: 12px;
  z-index: 1;
}
</style>
