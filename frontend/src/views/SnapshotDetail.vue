<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Download, Document } from '@element-plus/icons-vue'
import { marked } from 'marked'
import api from '../api/client'
import EmptyState from '../components/common/EmptyState.vue'

interface PresSlideInfo {
  slide_index: number
  layout_name: string
  status: string
  agent_outputs: Record<string, any> | null
}

const route = useRoute()
const router = useRouter()
const snapId = Number(route.params.id)

const snap = ref<any>(null)
const loading = ref(true)
const outlineSections = ref<any[]>([])
const presSlides = ref<PresSlideInfo[]>([])
const mkPreview = ref({ visible: false, html: '', filename: '' })
const downloading = ref(false)

onMounted(async () => {
  try {
    const { data } = await api.get(`/snapshots/${snapId}`)
    if (data.code === 0) {
      snap.value = data.data
      const oj = data.data.outline_json || {}
      outlineSections.value = oj.sections || []
      const pj = data.data.presentation_json || {}
      presSlides.value = pj.slides || []
    }
  } catch {
    ElMessage.error('加载快照失败')
  } finally {
    loading.value = false
  }
})

function getElementCount(outputs: Record<string, any> | null) {
  if (!outputs) return 0
  const elements = outputs.elements || outputs.elements
  return Array.isArray(elements) ? elements.length : 0
}

const statusLabel: Record<string, string> = {
  completed: '已完成',
  pending: '待生成',
  failed: '失败',
}

async function fetchMarkdownPreview() {
  try {
    const { data } = await api.get(`/export/outline/${snapId}/content`)
    if (data.code === 0) {
      mkPreview.value = {
        visible: true,
        html: marked(data.data.content) as string,
        filename: data.data.filename,
      }
    }
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '获取大纲内容失败')
  }
}

function downloadMarkdown() {
  // Download as .md source (not rendered HTML)
  const txt = document.querySelector('.mk-body')?.textContent || ''
  const blob = new Blob([txt], { type: 'text/markdown; charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = mkPreview.value.filename || `outline_snapshot_${snapId}.md`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('下载完成')
}

async function downloadPptx() {
  downloading.value = true
  try {
    const { data } = await api.get(`/export/presentation/${snapId}/content`)
    if (data.code === 0) {
      const byteChars = atob(data.data.content)
      const byteNums = new Array(byteChars.length)
      for (let i = 0; i < byteChars.length; i++) {
        byteNums[i] = byteChars.charCodeAt(i)
      }
      const blob = new Blob([new Uint8Array(byteNums)], {
        type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = data.data.filename || `presentation_snapshot_${snapId}.pptx`
      a.click()
      URL.revokeObjectURL(url)
      ElMessage.success('下载完成')
    }
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '导出 PPTX 失败')
  } finally {
    downloading.value = false
  }
}

function formatDate(d: string) {
  return new Date(d).toLocaleString('zh-CN')
}
</script>

<template>
  <div class="snap-page">
    <div class="snap-header">
      <el-button text @click="router.back()">← 返回</el-button>
      <h2>快照 #{{ snapId }}</h2>
    </div>

    <el-skeleton :loading="loading" :count="4" animated />

    <!-- Basic Info -->
    <div v-if="!loading && snap" class="snap-info">
      <el-descriptions :column="3" size="small" border>
        <el-descriptions-item label="版本">v{{ snap.version }}</el-descriptions-item>
        <el-descriptions-item label="大纲版本">v{{ snap.outline_version }}</el-descriptions-item>
        <el-descriptions-item label="幻灯片数">{{ presSlides.length || snap.presentation_json?.slide_count || 0 }} 页</el-descriptions-item>
        <el-descriptions-item label="创建时间" :span="3">{{ formatDate(snap.created_at) }}</el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- Action Buttons -->
    <div v-if="!loading && snap" class="snap-actions">
      <el-button type="primary" :icon="Document" @click="fetchMarkdownPreview">
        导出 Markdown 大纲
      </el-button>
      <el-button type="success" :icon="Download" :loading="downloading" @click="downloadPptx">
        下载 PPTX 文件
      </el-button>
    </div>

    <!-- Markdown Preview -->
    <div v-if="mkPreview.visible" class="mk-preview">
      <div class="mk-preview-header">
        <h3>大纲预览</h3>
        <el-button size="small" type="primary" @click="downloadMarkdown">保存到本地</el-button>
      </div>
      <div class="mk-body" v-html="mkPreview.html" />
    </div>

    <!-- Slide Embedded Preview -->
    <div v-if="!loading && presSlides.length > 0" class="slide-preview">
      <h3>幻灯片</h3>
      <div class="slide-grid">
        <el-card v-for="s in presSlides" :key="s.slide_index" class="slide-card" shadow="hover">
          <div class="slide-card-header">
            <span class="slide-idx">{{ s.slide_index }}</span>
            <span class="slide-layout">{{ s.layout_name }}</span>
            <el-tag :type="s.status === 'completed' ? 'success' : s.status === 'failed' ? 'danger' : 'info'" size="small">
              {{ statusLabel[s.status] || s.status }}
            </el-tag>
          </div>
          <div class="slide-card-body">{{ getElementCount(s.agent_outputs) }} 个元素</div>
        </el-card>
      </div>
    </div>

    <!-- Outline Structure (collapsible) -->
    <el-collapse v-if="!loading && outlineSections.length > 0" class="outline-collapse">
      <el-collapse-item title="大纲结构">
        <div v-for="sec in outlineSections" :key="sec.section_index" class="outline-sec">
          <h4>{{ sec.section_index }}. {{ sec.title }}</h4>
          <p v-if="sec.description" class="sec-desc">{{ sec.description }}</p>
          <ul v-if="sec.slides">
            <li v-for="sl in sec.slides" :key="sl.slide_index">
              {{ sl.slide_index }}. {{ sl.title }}
              <el-tag size="small" style="margin-left:6px">{{ sl.layout_type }}</el-tag>
            </li>
          </ul>
        </div>
      </el-collapse-item>
    </el-collapse>

    <EmptyState v-if="!loading && !snap" description="快照不存在" />
  </div>
</template>

<style scoped>
.snap-page { max-width: 900px; margin: 0 auto; padding: 24px; }
.snap-header { margin-bottom: 20px; }
.snap-header h2 { margin: 8px 0; }
.snap-info { margin-bottom: 20px; }
.snap-actions { display: flex; gap: 12px; margin-bottom: 24px; }

.mk-preview { margin-bottom: 24px; border: 1px solid #e4e7ed; border-radius: 8px; overflow: hidden; }
.mk-preview-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; background: var(--bg-hover); border-bottom: 1px solid var(--border); }
.mk-preview-header h3 { margin: 0; font-size: 15px; }
.mk-body { padding: 20px 24px; max-height: 600px; overflow-y: auto; line-height: 1.8; }
.mk-body :deep(h1) { font-size: 22px; }
.mk-body :deep(h2) { font-size: 18px; margin-top: 20px; }
.mk-body :deep(h3) { font-size: 16px; }
.mk-body :deep(ul) { padding-left: 20px; }

.slide-preview h3 { margin-bottom: 12px; }
.slide-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; margin-bottom: 24px; }
.slide-card-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.slide-idx { font-weight: 700; color: #409eff; font-size: 16px; min-width: 28px; }
.slide-layout { font-size: 13px; color: #909399; flex: 1; }
.slide-card-body { font-size: 13px; color: #606266; }

.outline-collapse { margin-top: 16px; }
.outline-sec { margin-bottom: 16px; }
.outline-sec h4 { margin: 0 0 4px; }
.sec-desc { font-size: 13px; color: #909399; margin: 0 0 8px; }
.outline-sec ul { margin: 0; padding-left: 20px; font-size: 14px; }
.outline-sec li { margin-bottom: 4px; }
</style>
