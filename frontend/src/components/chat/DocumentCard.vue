<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Download } from '@element-plus/icons-vue'
import api from '../../api/client'

const props = defineProps<{
  docType: string         // "outline" | "ppt"
  metadata: {
    outline_id?: number
    presentation_id?: number
    title?: string
  }
}>()

const router = useRouter()
const outline = ref<any>(null)
const ppt = ref<any>(null)
const loading = ref(false)

onMounted(async () => {
  if (props.docType === 'outline' && props.metadata.outline_id) {
    loading.value = true
    try {
      const { data } = await api.get(`/outline/${props.metadata.outline_id}`)
      if (data.code === 0) outline.value = data.data
    } catch { /* ignore */ }
    finally { loading.value = false }
  } else if (props.docType === 'ppt' && props.metadata.presentation_id) {
    loading.value = true
    try {
      const { data } = await api.get(`/ppt/${props.metadata.presentation_id}`)
      if (data.code === 0) ppt.value = data.data
    } catch { /* ignore */ }
    finally { loading.value = false }
  }
})

function viewOutline() {
  if (props.metadata.outline_id) router.push(`/outline/${props.metadata.outline_id}`)
}
function viewPpt() {
  if (props.metadata.presentation_id) router.push(`/ppt/${props.metadata.presentation_id}`)
}
function download() {
  if (props.metadata.presentation_id) {
    window.open(`/api/ppt/${props.metadata.presentation_id}/download`, '_blank')
  }
}
</script>

<template>
  <!-- Outline card -->
  <div v-if="docType === 'outline' && outline" class="doc-card outline">
    <div class="doc-header">
      <span class="doc-title">大纲: {{ outline.title }}</span>
      <div class="doc-tags">
        <el-tag size="small">v{{ outline.version }}</el-tag>
        <el-tag v-if="outline.eval_score != null" size="small" type="warning">
          {{ outline.eval_score.toFixed(2) }}
        </el-tag>
      </div>
    </div>
    <div class="doc-body">
      <span>共 {{ outline.slides?.length || outline.slide_count || 0 }} 页</span>
      <el-button size="small" type="primary" @click="viewOutline">查看大纲</el-button>
    </div>
  </div>

  <!-- PPT card -->
  <div v-if="docType === 'ppt' && ppt" class="doc-card ppt">
    <div class="doc-header">
      <span class="doc-title">PPT: {{ metadata.title || '已完成' }}</span>
      <el-tag size="small" :type="ppt.status === 'completed' ? 'success' : 'warning'">
        {{ ppt.status }}
      </el-tag>
    </div>
    <div class="doc-body">
      <span>{{ ppt.slide_count || 0 }} 页</span>
      <span v-if="ppt.file_size">{{ (ppt.file_size / 1024).toFixed(1) }} KB</span>
      <el-button size="small" type="primary" @click="viewPpt">查看</el-button>
      <el-button size="small" :icon="Download" @click="download">下载</el-button>
    </div>
  </div>

  <!-- Loading placeholder -->
  <div v-if="loading" class="doc-card loading">
    <p>加载 {{ docType === 'outline' ? '大纲' : 'PPT' }} 数据...</p>
  </div>
</template>

<style scoped>
.doc-card {
  padding: 16px;
  border-radius: 8px;
  margin-bottom: 16px;
  max-width: 420px;
}
.outline { background: #ecf5ff; border: 1px solid #d9ecff; }
.ppt { background: #f0f9eb; border: 1px solid #e1f3d8; }
.loading { background: #f5f7fa; border: 1px solid #e4e7ed; }
.doc-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.doc-title { font-weight: 600; }
.doc-tags { display: flex; gap: 6px; }
.outline .doc-title { color: #409eff; }
.ppt .doc-title { color: #67c23a; }
.doc-body {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  color: #909399;
}
</style>
