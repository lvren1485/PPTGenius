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

interface Snapshot {
  id: number
  version: number
  created_at: string
}

const route = useRoute()
const router = useRouter()
const pptId = Number(route.params.id)
const pres = ref<any>(null)
const slides = ref<PptSlide[]>([])
const snapshots = ref<Snapshot[]>([])
const loading = ref(true)
const snapLoading = ref(false)

const statusColors: Record<string, string> = {
  completed: 'success', pending: 'info',
  text_generating: 'warning', chart_generating: 'warning', failed: 'danger',
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

async function loadSnapshots() {
  if (snapshots.value.length > 0) return
  snapLoading.value = true
  try {
    const { data } = await api.get(`/ppt/${pptId}/snapshots`)
    if (data.code === 0) snapshots.value = data.data.snapshots || []
  } catch {
    ElMessage.error('加载快照失败')
  } finally {
    snapLoading.value = false
  }
}

function viewSnapshot(snapId: number) {
  router.push(`/snapshot/${snapId}`)
}

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

    <!-- Slides -->
    <el-skeleton :loading="loading" :count="4" animated />
    <EmptyState v-if="!loading && slides.length === 0" description="暂无 slide 数据" />
    <div v-if="!loading && slides.length > 0" class="ps-list">
      <el-card v-for="s in slides" :key="s.id" class="ps-item" shadow="hover">
        <div class="ps-header">
          <span class="ps-num">Slide {{ s.slide_index + 1 }}</span>
          <span>{{ s.layout_name }}</span>
          <el-tag :type="statusColors[s.status] || 'info'" size="small">{{ s.status }}</el-tag>
          <span v-if="s.retry_count" class="ps-retry">重试 {{ s.retry_count }} 次</span>
        </div>
        <div v-if="s.error_message" class="ps-error">{{ s.error_message }}</div>
      </el-card>
    </div>

    <!-- Snapshots -->
    <div v-if="!loading" class="snap-section">
      <div class="snap-header">
        <h3>版本快照</h3>
        <el-button link type="primary" :loading="snapLoading" @click="loadSnapshots">
          {{ snapshots.length > 0 ? `共 ${snapshots.length} 个` : '加载快照' }}
        </el-button>
      </div>
      <EmptyState v-if="snapLoading" description="加载中..." />
      <EmptyState v-else-if="snapshots.length === 0 && !snapLoading" description="点击上方加载快照" />
      <div v-else class="snap-list">
        <div v-for="snap in snapshots" :key="snap.id" class="snap-item" @click="viewSnapshot(snap.id)">
          <span>v{{ snap.version }}</span>
          <span class="snap-date">{{ new Date(snap.created_at).toLocaleString('zh-CN') }}</span>
          <el-button link type="primary" size="small">查看</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ppt-page {
  max-width: 900px;
  margin: 0 auto;
  padding: 24px;
}
.pp-header { margin-bottom: 24px; }
.pp-header h2 { margin: 8px 0 12px; }
.ps-list { display: flex; flex-direction: column; gap: 10px; }
.ps-header { display: flex; align-items: center; gap: 10px; }
.ps-num { font-weight: 700; color: #409eff; min-width: 80px; }
.ps-retry { font-size: 12px; color: #e6a23c; }
.ps-error {
  margin-top: 8px; font-size: 13px; color: #f56c6c;
  background: #fef0f0; padding: 8px; border-radius: 4px;
}
.snap-section {
  margin-top: 32px;
  border-top: 1px solid #e4e7ed;
  padding-top: 20px;
}
.snap-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
}
.snap-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.snap-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 16px;
  background: #f5f7fa;
  border-radius: 6px;
  cursor: pointer;
}
.snap-item:hover { background: #ecf5ff; }
.snap-date { flex: 1; font-size: 13px; color: #909399; }
</style>
