<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  phase: string
  detail: string
  slideIndex: number
  sending: boolean
}>()

defineEmits<{ stop: [] }>()

const phaseLabel = computed(() => {
  const m: Record<string, string> = {
    '正在分析需求...': '正在分析需求...',
    '正在搜索知识库...': '正在搜索知识库...',
    '正在生成大纲...': '正在生成大纲...',
    '正在评估大纲...': '正在评估大纲...',
    '正在选择样式...': '正在选择样式...',
    '正在生成幻灯片...': '正在生成幻灯片...',
  }
  return m[props.phase] || props.phase || '处理中...'
})

const progressText = computed(() => {
  if (props.slideIndex > 0) return `正在生成第 ${props.slideIndex} 页...`
  if (props.detail) return props.detail
  return ''
})
</script>

<template>
  <div class="sse-status">
    <div class="sse-top">
      <div class="sse-left">
        <el-tag type="primary" size="small" effect="dark">{{ phaseLabel }}</el-tag>
        <span class="sse-detail" v-if="progressText">{{ progressText }}</span>
      </div>
      <el-button
        v-if="sending"
        type="danger"
        size="small"
        text
        @click="$emit('stop')"
      >
        停止生成
      </el-button>
    </div>
    <el-skeleton v-if="sending && !progressText" :rows="1" animated style="margin-top:6px" />
    <el-progress
      v-if="slideIndex > 0"
      :percentage="0"
      :indeterminate="true"
      :stroke-width="4"
      :show-text="false"
      style="margin-top: 6px"
    />
  </div>
</template>

<style scoped>
.sse-status {
  background: #ecf5ff;
  border-top: 1px solid #d9ecff;
  padding: 10px 24px;
  flex-shrink: 0;
}
.sse-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.sse-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.sse-detail {
  font-size: 13px;
  color: #606266;
}
</style>
