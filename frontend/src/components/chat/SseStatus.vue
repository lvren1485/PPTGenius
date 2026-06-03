<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  phase: string
  step: string
  detail: string
  pct: number
}>()

const phaseLabel = computed(() => {
  const m: Record<string, string> = {
    loading_state: '加载中',
    coordinator_decision: '分析中',
    searching_knowledge: '检索知识库',
    searching_web: '搜索网络',
    fetching_web: '获取网页',
    writing_outline: '生成大纲',
    evaluating: '评估中',
    slide_generating: '生成页面',
    slide_done: '页面完成',
    ppt: 'PPT生成',
    ppt_done: 'PPT完成',
  }
  return m[props.step] || props.step || props.phase || ''
})

const pctSafe = computed(() => Math.min(100, Math.max(0, props.pct || 0)))
</script>

<template>
  <div v-if="phase || step" class="sse-status">
    <div class="sse-row">
      <el-tag size="small" :type="pctSafe === 100 ? 'success' : 'primary'">
        {{ phaseLabel }}
      </el-tag>
      <span class="sse-detail">{{ detail }}</span>
    </div>
    <el-progress
      v-if="pctSafe > 0"
      :percentage="pctSafe"
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
.sse-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.sse-detail {
  font-size: 13px;
  color: #606266;
}
</style>
