<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { CopyDocument, Clock, Download } from '@element-plus/icons-vue'
import { marked } from 'marked'
import api from '../api/client'
import EmptyState from '../components/common/EmptyState.vue'

interface Slide {
  id: number; slide_index: number; title: string
  content_json: Record<string, any> | null; layout_type: string | null
  has_image: boolean | null; has_chart: boolean | null; notes: string | null
}

interface SnapItem { id: number; version: number; created_at: string }

const route = useRoute()
const router = useRouter()
const outlineId = Number(route.params.id)
const outline = ref<any>(null)
const slides = ref<Slide[]>([])
const loading = ref(true)

// Snapshots
const snaps = ref<SnapItem[]>([])
const snapsLoading = ref(false)
const dialogVisible = ref(false)
const dialogTitle = ref('')
const mkHtml = ref('')
const mkSource = ref('')
const mkFilename = ref('')

onMounted(async () => {
  try {
    const { data } = await api.get(`/outline/${outlineId}`)
    if (data.code === 0) {
      outline.value = data.data
      slides.value = data.data.slides || []
    }
  } catch { ElMessage.error('加载大纲失败') }
  finally { loading.value = false }

  // Load snapshots in background
  loadSnapshots()
})

async function loadSnapshots() {
  snapsLoading.value = true
  try {
    const { data } = await api.get(`/export/outline-snapshots/${outlineId}`)
    if (data.code === 0) snaps.value = data.data.snapshots || []
  } catch { /* ignore */ }
  finally { snapsLoading.value = false }
}

async function openSnapshot(snapId: number, ver: number) {
  dialogVisible.value = true
  dialogTitle.value = `v${ver}`
  mkHtml.value = ''
  mkSource.value = ''
  try {
    const { data } = await api.get(`/export/outline/${snapId}/content`)
    if (data.code === 0) {
      mkSource.value = data.data.content
      mkHtml.value = marked(data.data.content) as string
      mkFilename.value = data.data.filename
    }
  } catch { ElMessage.error('加载快照失败') }
}

function downloadMarkdown() {
  const blob = new Blob([mkSource.value], { type: 'text/markdown; charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = mkFilename.value || `outline_v${dialogTitle.value.replace('v','')}.md`
  a.click()
  URL.revokeObjectURL(url)
}

function copyOutline() {
  if (!outline.value) return
  const lines: string[] = [`大纲: ${outline.value.title}`, '']
  slides.value.forEach((s, i) => {
    lines.push(`Slide ${i + 1}: ${s.title}`)
    const content = formatContent(s.content_json)
    if (content) lines.push(`  ${content}`)
    if (s.notes) lines.push(`  备注: ${s.notes}`)
    lines.push('')
  })
  navigator.clipboard.writeText(lines.join('\n')).then(() => ElMessage.success('已复制到剪贴板'))
}

function formatContent(c: Record<string, any> | null) {
  if (!c) return ''
  const parts: string[] = []
  if (c.main_points?.length) parts.push('要点: ' + c.main_points.join(' · '))
  if (c.key_data) parts.push('数据: ' + c.key_data)
  if (c.recommended_ppt_format) parts.push('格式: ' + c.recommended_ppt_format)
  if (c.subtitle) parts.push('副标题: ' + c.subtitle)
  return parts.join(' | ')
}

function formatDate(d: string) { return new Date(d).toLocaleString('zh-CN') }
</script>

<template>
  <div class="outline-page">
    <div class="op-header">
      <el-button text @click="router.back()">← 返回</el-button>
      <h2 v-if="outline">{{ outline.title }}</h2>
      <div v-if="outline" class="op-meta">
        <el-tag>v{{ outline.version }}</el-tag>
        <el-tag type="warning" v-if="outline.eval_score != null">评分 {{ outline.eval_score }}</el-tag>
        <span>{{ slides.length }} 页</span>
        <el-button text :icon="CopyDocument" size="small" @click="copyOutline">复制</el-button>
      </div>
    </div>

    <!-- Snapshots Section -->
    <div class="snap-section">
      <h3 class="section-title">历史快照</h3>
      <div v-if="snapsLoading" class="snap-loading">加载中...</div>
      <EmptyState v-else-if="snaps.length === 0" description="暂无快照" />
      <div v-else class="snap-cards">
        <div
          v-for="s in snaps" :key="s.id"
          class="snap-card"
          @click="openSnapshot(s.id, s.version)"
        >
          <el-icon :size="18"><Clock /></el-icon>
          <span class="snap-ver">v{{ s.version }}</span>
          <span class="snap-time">{{ formatDate(s.created_at) }}</span>
          <el-tag size="small" type="primary">查看</el-tag>
        </div>
      </div>
    </div>

    <!-- Outline Detail Section -->
    <h3 class="section-title">大纲内容</h3>
    <el-skeleton :loading="loading" :count="4" animated />
    <EmptyState v-if="!loading && slides.length === 0" description="暂无内容" />
    <div v-if="!loading" class="slide-list">
      <el-card v-for="s in slides" :key="s.id" class="slide-item" shadow="hover">
        <div class="slide-header">
          <span class="slide-num">Slide {{ s.slide_index + 1 }}</span>
          <span class="slide-title-text">{{ s.title }}</span>
          <el-tag size="small">{{ s.layout_type }}</el-tag>
          <el-tag v-if="s.has_image" size="small" type="success">有图片</el-tag>
          <el-tag v-if="s.has_chart" size="small" type="warning">有图表</el-tag>
        </div>
        <div v-if="formatContent(s.content_json)" class="slide-content">{{ formatContent(s.content_json) }}</div>
        <div v-if="s.notes" class="slide-notes">备注: {{ s.notes }}</div>
      </el-card>
    </div>
  </div>

  <!-- Snapshot preview dialog -->
  <el-dialog v-model="dialogVisible" :title="`大纲快照 ${dialogTitle}`" width="80%" top="4vh" destroy-on-close>
    <div class="dlg-mk-body" v-html="mkHtml" />
    <template #footer>
      <el-button :icon="Download" @click="downloadMarkdown">下载 Markdown</el-button>
      <el-button type="primary" @click="dialogVisible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.outline-page { max-width: 800px; margin: 0 auto; padding: 24px; }
.op-header { margin-bottom: 24px; }
.op-header h2 { margin: 8px 0; }
.op-meta { display: flex; align-items: center; gap: 10px; color: #909399; }
.section-title { font-size: 17px; margin: 28px 0 14px; color: #303133; }

/* Snapshots */
.snap-section { margin-bottom: 12px; }
.snap-loading { color: #909399; font-size: 13px; padding: 8px 0; }
.snap-cards { display: flex; flex-wrap: wrap; gap: 10px; }
.snap-card {
  display: flex; align-items: center; gap: 10px;
  padding: 12px 18px; background: var(--primary-bg); border: 1px solid var(--primary-border);
  border-radius: 10px; cursor: pointer; transition: box-shadow .15s;
}
.snap-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,.06); }
.snap-ver { font-weight: 600; color: #409eff; font-size: 14px; }
.snap-time { font-size: 13px; color: #909399; }

/* Slides */
.slide-list { display: flex; flex-direction: column; gap: 12px; }
.slide-item { padding: 4px 0; }
.slide-header { display: flex; align-items: center; gap: 10px; }
.slide-num { font-weight: 700; color: #409eff; min-width: 70px; }
.slide-title-text { font-weight: 600; flex: 1; }
.slide-content { margin-top: 10px; font-size: 14px; color: #606266; }
.slide-notes { margin-top: 8px; font-size: 13px; color: #c0c4cc; }
</style>

<style>
.dlg-mk-body {
  font-size: 16px; line-height: 1.9; color: var(--text);
  max-height: 70vh; overflow-y: auto; padding: 0 8px;
}
.dlg-mk-body h1 { font-size: 26px; margin: 0 0 16px; }
.dlg-mk-body h2 { font-size: 20px; margin: 24px 0 12px; border-bottom: 1px solid var(--border); padding-bottom: 8px; position: sticky; top: 0; background: var(--bg-card); z-index: 2; }
.dlg-mk-body h3 { font-size: 17px; margin: 18px 0 8px; position: sticky; top: 0; background: var(--bg-card); z-index: 1; }
.dlg-mk-body ul, .dlg-mk-body ol { padding-left: 24px; margin: 8px 0; }
.dlg-mk-body li { margin-bottom: 6px; }
.dlg-mk-body p { margin: 8px 0; }
.dlg-mk-body strong { color: var(--primary); }
.dlg-mk-body em { color: var(--text-muted); }
</style>
