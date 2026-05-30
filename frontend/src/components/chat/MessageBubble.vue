<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'

const props = defineProps<{
  role: string
  content: string
  content_type: string | null
  createdAt: string
}>()

const isUser = computed(() => props.role === 'user')
const isAssistant = computed(() => props.role === 'assistant')

function renderMarkdown(text: string): string {
  return marked(text, { breaks: true }) as string
}

function formatTime(d: string) {
  return new Date(d).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <div class="msg-bubble" :class="{ 'is-user': isUser, 'is-assistant': isAssistant }">
    <div class="msg-role">{{ isUser ? '我' : 'AI' }}</div>
    <div class="msg-body">
      <div v-if="isAssistant" class="msg-content" v-html="renderMarkdown(content)" />
      <div v-else class="msg-content">{{ content }}</div>
    </div>
    <div class="msg-time">{{ formatTime(createdAt) }}</div>
  </div>
</template>

<style scoped>
.msg-bubble {
  display: flex;
  flex-direction: column;
  margin-bottom: 20px;
  max-width: 80%;
}
.is-user {
  align-self: flex-end;
  align-items: flex-end;
}
.is-assistant {
  align-self: flex-start;
}
.msg-role {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}
.msg-body {
  padding: 12px 16px;
  border-radius: 12px;
  line-height: 1.6;
}
.is-user .msg-body {
  background: #409eff;
  color: #fff;
}
.is-assistant .msg-body {
  background: #fff;
  border: 1px solid #e4e7ed;
}
.msg-content :deep(p) { margin: 0 0 8px; }
.msg-content :deep(p:last-child) { margin: 0; }
.msg-content :deep(pre) {
  background: #f5f7fa;
  border-radius: 6px;
  padding: 12px;
  overflow-x: auto;
  font-size: 13px;
}
.msg-content :deep(code) {
  font-family: 'Fira Code', monospace;
  font-size: 13px;
}
.msg-time {
  font-size: 12px;
  color: #c0c4cc;
  margin-top: 4px;
}
</style>
