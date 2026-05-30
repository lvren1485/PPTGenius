<script setup lang="ts">
import { useRouter } from 'vue-router'

const props = defineProps<{ pptData: Record<string, any> }>()
const router = useRouter()
const d = props.pptData

function download() {
  window.open(`/api/ppt/${d.presentation_id}/download`, '_blank')
}
function viewPpt() {
  router.push(`/ppt/${d.presentation_id}`)
}
</script>

<template>
  <div class="ppt-card">
    <div class="pc-header">
      <span class="pc-title">PPT 已就绪</span>
      <el-tag size="small" type="success">已完成</el-tag>
    </div>
    <div class="pc-info" v-if="d.slide_count">共 {{ d.slide_count }} 页</div>
    <div class="pc-info" v-if="d.elapsed_seconds">耗时 {{ d.elapsed_seconds }}s</div>
    <div class="pc-actions">
      <el-button size="small" type="primary" @click="viewPpt">查看 PPT</el-button>
      <el-button size="small" @click="download">下载</el-button>
    </div>
  </div>
</template>

<style scoped>
.ppt-card {
  background: #f0f9eb;
  border: 1px solid #e1f3d8;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
  max-width: 400px;
}
.pc-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.pc-title {
  font-weight: 600;
  color: #67c23a;
}
.pc-info {
  font-size: 13px;
  color: #909399;
  margin-bottom: 4px;
}
.pc-actions {
  margin-top: 12px;
  display: flex;
  gap: 8px;
}
</style>
