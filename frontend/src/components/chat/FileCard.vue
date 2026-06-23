<script setup lang="ts">
import { Document } from '@element-plus/icons-vue'

defineProps<{ content: string; createdAt: string }>()

function parseInfo(content: string) {
  const lines = content.split('\n')
  const name = lines[0]?.replace('[File uploaded: ', '').replace(']', '') || ''
  const typeLine = lines[1] || ''
  const preview = lines.slice(3).join('\n').slice(0, 300)
  return { name, typeLine, preview }
}

function formatTime(d: string) {
  return new Date(d).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <div class="file-card">
    <div class="file-header">
      <el-icon :size="20"><Document /></el-icon>
      <span class="file-name">{{ parseInfo(content).name }}</span>
    </div>
    <div class="file-meta">{{ parseInfo(content).typeLine }}</div>
    <div v-if="parseInfo(content).preview" class="file-preview">
      {{ parseInfo(content).preview }}...
    </div>
    <div class="file-time">{{ formatTime(createdAt) }}</div>
  </div>
</template>

<style scoped>
.file-card {
  background: var(--success-bg);
  border: 1px solid #e1f3d8;
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 16px;
  max-width: 360px;
}
.file-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: #67c23a;
}
.file-meta {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
.file-preview {
  font-size: 13px;
  color: #606266;
  margin-top: 8px;
  padding: 8px;
  background: var(--bg-card);
  border-radius: 4px;
  max-height: 120px;
  overflow: hidden;
}
.file-time {
  font-size: 12px;
  color: #c0c4cc;
  margin-top: 6px;
}
</style>
