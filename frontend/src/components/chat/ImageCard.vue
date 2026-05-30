<script setup lang="ts">
import { Picture } from '@element-plus/icons-vue'

defineProps<{ content: string; createdAt: string }>()

function parseInfo(content: string) {
  const lines = content.split('\n')
  const name = lines[0]?.replace('[Image uploaded: ', '').replace(']', '') || ''
  const path = lines[1]?.replace('Path: ', '') || ''
  const typeLine = lines[2]?.replace('Type: ', '') || ''
  return { name, path, typeLine }
}

function formatTime(d: string) {
  return new Date(d).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <div class="image-card">
    <div class="image-header">
      <el-icon :size="20"><Picture /></el-icon>
      <span>{{ parseInfo(content).name }}</span>
    </div>
    <div class="image-meta">{{ parseInfo(content).path }}</div>
    <div class="image-type">{{ parseInfo(content).typeLine }}</div>
    <div class="image-time">{{ formatTime(createdAt) }}</div>
  </div>
</template>

<style scoped>
.image-card {
  background: #fdf6ec;
  border: 1px solid #faecd8;
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 16px;
  max-width: 300px;
}
.image-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: #e6a23c;
}
.image-meta {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
.image-type {
  font-size: 12px;
  color: #c0c4cc;
  margin-top: 2px;
}
.image-time {
  font-size: 12px;
  color: #c0c4cc;
  margin-top: 6px;
}
</style>
