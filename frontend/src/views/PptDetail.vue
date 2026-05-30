<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api/client'
import EmptyState from '../components/common/EmptyState.vue'

interface PptSlide {
  id: number
  slide_index: number
  layout_name: string
  status: string
  retry_count: number
  agent_outputs: Record<string, any> | null
  error_message: string | null
}

const route = useRoute()
const router = useRouter()
const pptId = Number(route.params.id)
const pres = ref<any>(null)
const slides = ref<PptSlide[]>([])
const loading = ref(true)
const activeSlide = ref(0)

const statusColors: Record<string, string> = {
  completed: 'success',
  pending: 'info',
  text_generating: 'warning',
  chart_generating: 'warning',
  failed: 'danger',
}

onMounted(async () => {
  try {
    const [presResp, slidesResp] = await Promise.all([
      api.get(`/ppt/${pptId}`),
      api.get(`/ppt/${pptId}/slides`),
    ])
    if (presResp.data.code === 0) pres.value = presResp.data.data
    if (slidesResp.data.code === 0) slides.value = slidesResp.data.data.slides || []
  } catch {
    ElMessage.error('加载 PPT 失败')
  } finally {
    loading.value = false
  }
})

function download() {
  window.open(`/api/ppt/${pptId}/download`, '_blank')
}

function formatSize(bytes: number) {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes} B`
  return `${(bytes / 1024).toFixed(1)} KB`
}
</script>

<template>
  <div class="ppt-page">
    <div class="pp-header">
      <el-button text @click="router.back()">← 返回</el-button>
      <h2 v-if="pres">PPT 预览</h2>
      <div v-if="pres" class="pp-meta">
        <el-descriptions :column="5" size="small" border>
          <el-descriptions-item label="状态">
            <el-tag :type="statusColors[pres.status] || 'info'" size="small">
              {{ pres.status }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="页数">{{ pres.slide_count || slides.length }}</el-descriptions-item>
          <el-descriptions-item label="大小">{{ formatSize(pres.file_size) }}</el-descriptions-item>
          <el-descriptions-item label="模板">ID: {{ pres.template_id || 'default' }}</el-descriptions-item>
          <el-descriptions-item label="配色">ID: {{ pres.color_scheme_id || 'default' }}</el-descriptions-item>
        </el-descriptions>
      </div>
      <el-button type="primary" @click="download" style="margin-top:12px">下载 .pptx</el-button>
    </div>

    <el-skeleton :loading="loading" :count="4" animated />
    <EmptyState v-if="!loading && slides.length === 0" description="暂无 slide 数据" />
    <div v-if="!loading && slides.length > 0" class="ps-list">
      <el-card
        v-for="s in slides"
        :key="s.id"
        class="ps-item"
        shadow="hover"
      >
        <div class="ps-header">
          <span class="ps-num">Slide {{ s.slide_index + 1 }}</span>
          <span>{{ s.layout_name }}</span>
          <el-tag :type="statusColors[s.status] || 'info'" size="small">
            {{ s.status }}
          </el-tag>
          <span v-if="s.retry_count" class="ps-retry">重试 {{ s.retry_count }} 次</span>
        </div>
        <div v-if="s.error_message" class="ps-error">
          {{ s.error_message }}
        </div>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.ppt-page {
  max-width: 900px;
  margin: 0 auto;
  padding: 24px;
}
.pp-header {
  margin-bottom: 24px;
}
.pp-header h2 {
  margin: 8px 0 12px;
}
.ps-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.ps-header {
  display: flex;
  align-items: center;
  gap: 10px;
}
.ps-num {
  font-weight: 700;
  color: #409eff;
  min-width: 80px;
}
.ps-retry {
  font-size: 12px;
  color: #e6a23c;
}
.ps-error {
  margin-top: 8px;
  font-size: 13px;
  color: #f56c6c;
  background: #fef0f0;
  padding: 8px;
  border-radius: 4px;
}
</style>
