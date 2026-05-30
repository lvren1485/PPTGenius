<script setup lang="ts">
import { useRouter } from 'vue-router'

const props = defineProps<{ outlineData: Record<string, any> }>()
const router = useRouter()
const o = props.outlineData

function viewOutline() {
  router.push(`/outline/${o.outline_id}`)
}
</script>

<template>
  <div class="outline-card">
    <div class="oc-header">
      <span class="oc-title">大纲: {{ o.title }}</span>
      <el-tag size="small">v{{ o.version }}</el-tag>
      <el-tag v-if="o.eval_score != null" size="small" type="warning">
        评分 {{ o.eval_score }}
      </el-tag>
    </div>
    <div class="oc-info">共 {{ o.slide_count || (o.slides ? o.slides.length : 0) }} 页</div>
    <el-button size="small" type="primary" @click="viewOutline">查看大纲</el-button>
  </div>
</template>

<style scoped>
.outline-card {
  background: #ecf5ff;
  border: 1px solid #d9ecff;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
  max-width: 400px;
}
.oc-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.oc-title {
  font-weight: 600;
  color: #409eff;
}
.oc-info {
  font-size: 13px;
  color: #909399;
  margin-bottom: 12px;
}
</style>
