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
  <div class="msg-bubble" :class="{ 'is-user': isUser, 'is-assistant': isAssistant, 'is-loading': isAssistant && content === '...' }">
    <div class="msg-role">{{ isUser ? '我' : 'AI' }}</div>
    <div class="msg-body">
      <div v-if="isAssistant && content === '...'" class="msg-content loading-dots">
        <span></span><span></span><span></span>
      </div>
      <div v-else-if="isAssistant" class="msg-content" v-html="renderMarkdown(content)" />
      <div v-else class="msg-content">{{ content }}</div>
    </div>
    <div class="msg-time" v-if="content !== '...'">{{ formatTime(createdAt) }}</div>
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
  padding: 16px 24px 16px 28px;
  border-radius: 12px;
  line-height: 1.7;
}
.is-user .msg-body {
  background: #409eff;
  color: #fff;
  padding: 12px 20px;
}
.is-assistant .msg-body {
  background: #fafbfc;
  border: 1px solid #e8eaed;
}
.msg-content {
  word-break: break-word;
  overflow-wrap: break-word;
}
.msg-content :deep(p) { margin: 0 0 8px; }
.msg-content :deep(p:last-child) { margin: 0; }
.msg-content :deep(ol), .msg-content :deep(ul) {
  padding-left: 0;
  margin-left: 0;
  list-style-position: inside;
}
.msg-content :deep(ol li), .msg-content :deep(ul li) {
  margin-bottom: 4px;
  word-break: break-word;
}
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
.is-loading .msg-body {
  background: #fafbfc;
  border-color: #e4e7ed;
  min-width: 80px;
}
.loading-dots {
  display: flex;
  gap: 6px;
  align-items: center;
  justify-content: center;
  padding: 6px 0;
}
.loading-dots span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #c0c4cc;
  animation: bounce 1.4s ease-in-out infinite both;
}
.loading-dots span:nth-child(1) { animation-delay: 0s; }
.loading-dots span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}
</style>
