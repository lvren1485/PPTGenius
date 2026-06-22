<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Clock, Download } from '@element-plus/icons-vue'
import api from '../api/client'
import EmptyState from '../components/common/EmptyState.vue'

interface PptSlide {
  id: number; slide_index: number; layout_name: string
  status: string; agent_outputs: Record<string, any> | null
}

interface SnapItem { id: number; version: number; created_at: string }

const route = useRoute()
const router = useRouter()
const pptId = Number(route.params.id)
const pres = ref<any>(null)
const slides = ref<PptSlide[]>([])
const loading = ref(true)

// Snapshots
const snaps = ref<SnapItem[]>([])
const snapsLoading = ref(false)
const dialogVisible = ref(false)
const dialogTitle = ref('')
const currentSnapId = ref(0)
const snapSlides = ref<PptSlide[]>([])
const snapSlideCount = ref(0)
const snapDownloading = ref(false)

onMounted(async () => {
  try {
    const [presResp, slidesResp] = await Promise.all([
      api.get(`/ppt/${pptId}`),
      api.get(`/ppt/${pptId}/slides`),
    ])
    if (presResp.data.code === 0) pres.value = presResp.data.data
    if (slidesResp.data.code === 0) slides.value = slidesResp.data.data.slides || []
  } catch { ElMessage.error('加载 PPT 失败') }
  finally { loading.value = false }

  loadSnapshots()
})

async function loadSnapshots() {
  snapsLoading.value = true
  try {
    const { data } = await api.get(`/ppt/${pptId}/snapshots`)
    if (data.code === 0) snaps.value = data.data.snapshots || []
  } catch { /* ignore */ }
  finally { snapsLoading.value = false }
}

async function openSnapshot(snapId: number, ver: number) {
  dialogVisible.value = true
  dialogTitle.value = `v${ver}`
  currentSnapId.value = snapId
  snapSlides.value = []
  try {
    const { data } = await api.get(`/snapshots/${snapId}`)
    if (data.code === 0) {
      const pj = data.data.presentation_json || {}
      snapSlides.value = pj.slides || []
      snapSlideCount.value = pj.slide_count || snapSlides.value.length
    }
  } catch { ElMessage.error('加载快照失败') }
}

async function downloadPptx(snapId: number) {
  snapDownloading.value = true
  try {
    const { data } = await api.get(`/export/presentation/${snapId}/content`)
    if (data.code === 0) {
      const byteChars = atob(data.data.content)
      const byteNums = new Array(byteChars.length)
      for (let i = 0; i < byteChars.length; i++) byteNums[i] = byteChars.charCodeAt(i)
      const blob = new Blob([new Uint8Array(byteNums)], {
        type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = data.data.filename || `presentation_v${snapId}.pptx`
      a.click()
      URL.revokeObjectURL(url)
      ElMessage.success('下载完成')
    }
  } catch { ElMessage.error('下载失败') }
  finally { snapDownloading.value = false }
}

function getElementCount(out: Record<string, any> | null) {
  if (!out) return 0
  const el = out.elements
  return Array.isArray(el) ? el.length : 0
}

const statusLabel: Record<string, string> = { completed: '已完成', pending: '待生成', failed: '失败' }
function formatDate(d: string) { return new Date(d).toLocaleString('zh-CN') }
function formatSize(b: number) { if (!b) return ''; return b < 1024 ? `${b} B` : `${(b / 1024).toFixed(1)} KB` }

function download() { window.open(`/api/ppt/${pptId}/download`, '_blank') }
</script>

<template>
  <div class="ppt-page">
    <div class="pp-header">
      <el-button text @click="router.back()">← 返回</el-button>
      <h2 v-if="pres">PPT 预览</h2>
      <div v-if="pres" class="pp-meta">
        <el-descriptions :column="3" size="small" border>
          <el-descriptions-item label="状态">
            <el-tag :type="pres.status === 'completed' ? 'success' : 'warning'" size="small">{{ pres.status }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="页数">{{ pres.slide_count || slides.length }}</el-descriptions-item>
          <el-descriptions-item label="大小">{{ formatSize(pres.file_size) }}</el-descriptions-item>
          <el-descriptions-item label="版本">v{{ pres.version }}</el-descriptions-item>
          <el-descriptions-item label="大纲版本">v{{ pres.outline_version }}</el-descriptions-item>
          <el-descriptions-item label="样式">{{ '#' + (pres.style_id || '默认') }}</el-descriptions-item>
        </el-descriptions>
      </div>
      <el-button type="primary" @click="download" style="margin-top:12px">下载 .pptx</el-button>
    </div>

    <!-- Snapshots Section -->
    <div class="snap-section">
      <h3 class="section-title">历史快照</h3>
      <div v-if="snapsLoading" class="snap-loading">加载中...</div>
      <EmptyState v-else-if="snaps.length === 0" description="暂无快照" />
      <div v-else class="snap-cards">
        <div v-for="s in snaps" :key="s.id" class="snap-card" @click="openSnapshot(s.id, s.version)">
          <el-icon :size="18"><Clock /></el-icon>
          <span class="snap-ver">v{{ s.version }}</span>
          <span class="snap-time">{{ formatDate(s.created_at) }}</span>
          <el-tag size="small" type="success">查看</el-tag>
        </div>
      </div>
    </div>

    <!-- Slides Section -->
    <h3 class="section-title">幻灯片</h3>
    <el-skeleton :loading="loading" :count="4" animated />
    <EmptyState v-if="!loading && slides.length === 0" description="暂无 slide 数据" />
    <div v-if="!loading && slides.length > 0" class="ps-list">
      <el-card v-for="s in slides" :key="s.id" class="ps-item" shadow="hover">
        <div class="ps-header">
          <span class="ps-num">Slide {{ s.slide_index + 1 }}</span>
          <span>{{ s.layout_name }}</span>
          <el-tag :type="s.status === 'completed' ? 'success' : s.status === 'failed' ? 'danger' : 'info'" size="small">
            {{ statusLabel[s.status] || s.status }}
          </el-tag>
        </div>
      </el-card>
    </div>
  </div>

  <!-- Snapshot preview dialog -->
  <el-dialog v-model="dialogVisible" :title="`PPT 快照 ${dialogTitle}`" width="80%" top="4vh" destroy-on-close>
    <div class="dlg-info">
      <span>{{ snapSlides.length || snapSlideCount }} 页</span>
    </div>
    <div class="dlg-slide-grid">
      <el-card v-for="s in snapSlides" :key="s.slide_index" class="dlg-slide" shadow="hover">
        <div class="dlg-slide-header">
          <span class="dlg-slide-idx">{{ s.slide_index }}</span>
          <span>{{ s.layout_name }}</span>
          <el-tag :type="s.status === 'completed' ? 'success' : 'info'" size="small">
            {{ statusLabel[s.status] || s.status }}
          </el-tag>
        </div>
        <div class="dlg-slide-body">{{ getElementCount(s.agent_outputs) }} 个元素</div>
      </el-card>
    </div>
    <template #footer>
      <el-button :icon="Download" :loading="snapDownloading" @click="downloadPptx(currentSnapId)">
        下载 PPTX
      </el-button>
      <el-button type="primary" @click="dialogVisible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.ppt-page { max-width: 900px; margin: 0 auto; padding: 24px; }
.pp-header { margin-bottom: 24px; }
.pp-header h2 { margin: 8px 0 12px; }
.section-title { font-size: 17px; margin: 28px 0 14px; color: #303133; }

/* Snapshots */
.snap-loading { color: #909399; font-size: 13px; padding: 8px 0; }
.snap-cards { display: flex; flex-wrap: wrap; gap: 10px; }
.snap-card {
  display: flex; align-items: center; gap: 10px;
  padding: 12px 18px; background: #f0f9eb; border: 1px solid #e1f3d8;
  border-radius: 10px; cursor: pointer; transition: box-shadow .15s;
}
.snap-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,.06); }
.snap-ver { font-weight: 600; color: #67c23a; font-size: 14px; }
.snap-time { font-size: 13px; color: #909399; }

/* Slides */
.ps-list { display: flex; flex-direction: column; gap: 10px; }
.ps-header { display: flex; align-items: center; gap: 10px; }
.ps-num { font-weight: 700; color: #409eff; min-width: 80px; }

/* Dialog */
.dlg-info { margin-bottom: 16px; color: #909399; font-size: 14px; }
.dlg-slide-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; max-height: 60vh; overflow-y: auto; }
.dlg-slide-header { display: flex; align-items: center; gap: 8px; }
.dlg-slide-idx { font-weight: 700; color: #67c23a; font-size: 16px; min-width: 24px; }
.dlg-slide-body { font-size: 13px; color: #909399; margin-top: 4px; }
</style>
