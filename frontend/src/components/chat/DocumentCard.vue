<script setup lang="ts">
import { ref, computed } from 'vue'
import { Download, Document } from '@element-plus/icons-vue'
import { marked } from 'marked'
import api from '../../api/client'
import PptPreview from './PptPreview.vue'

const props = defineProps<{
  docType: string
  metadata: { outline_id?: number; presentation_id?: number; title?: string; version?: number }
  content: string
}>()

const dialogVisible = ref(false)
const mkHtml = ref('')
const mkSource = ref('')
const mkFilename = ref('')
const loading = ref(false)
const pptPreviewVisible = ref(false)
const pptPreviewSnapId = ref(0)

const title = computed(() => props.metadata.title || props.content || '')
const version = computed(() => props.metadata.version)
const snapId = computed(() => {
  if (props.metadata.outline_id) return props.metadata.outline_id
  if (props.metadata.presentation_id) return props.metadata.presentation_id
  const n = Number(props.content)
  return isNaN(n) ? 0 : n
})

const isOutline = computed(() => props.docType === 'outline')

async function openDialog() {
  if (!isOutline.value) {
    if (snapId.value > 0) { pptPreviewSnapId.value = snapId.value; pptPreviewVisible.value = true }
    return
  }
  if (!mkSource.value) await fetchMarkdown()
  if (mkSource.value) dialogVisible.value = true
}

async function fetchMarkdown() {
  if (!snapId.value) return
  loading.value = true
  try {
    const { data } = await api.get(`/export/outline/${snapId.value}/content`)
    if (data.code === 0) {
      mkSource.value = data.data.content
      mkHtml.value = marked(data.data.content) as string
      mkFilename.value = data.data.filename
    }
  } catch { /* ignore */ }
  finally { loading.value = false }
}

function downloadMarkdown() {
  const blob = new Blob([mkSource.value], { type: 'text/markdown; charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = mkFilename.value || `outline_${snapId.value}.md`
  a.click()
  URL.revokeObjectURL(url)
}

</script>

<template>
  <!-- Card -->
  <div class="doc-card" :class="[isOutline ? 'outline' : 'ppt', loading ? 'card-loading' : '']" @click="openDialog">
    <div class="doc-header">
      <el-icon :size="18"><Document /></el-icon>
      <span class="doc-title">{{ isOutline ? '大纲' : 'PPT' }}：{{ title }}{{ version != null ? ` v${version}` : '' }}</span>
      <el-tag size="small" :type="isOutline ? 'primary' : 'success'">
        {{ isOutline ? '大纲' : 'PPT' }}
      </el-tag>
    </div>
    <div v-if="loading" class="card-loader"><div class="loader-bar" /></div>
    <div class="doc-actions" v-if="snapId > 0">
      <template v-if="isOutline">
        <el-button size="small" text type="primary" :loading="loading" @click.stop="openDialog">
          查看大纲
        </el-button>
        <el-button v-if="mkSource" size="small" text :icon="Download" @click.stop="downloadMarkdown">
          下载
        </el-button>
      </template>
      <template v-else>
        <el-button size="small" text type="primary" @click.stop="pptPreviewSnapId = snapId; pptPreviewVisible = true">
          预览 PPT
        </el-button>
      </template>
    </div>
  </div>

  <PptPreview :snap-id="pptPreviewSnapId" :visible="pptPreviewVisible" @close="pptPreviewVisible = false" />

  <!-- Outline preview dialog -->
  <el-dialog
    v-model="dialogVisible"
    :title="`大纲预览：${title}`"
    width="80%"
    top="4vh"
    destroy-on-close
  >
    <div class="dlg-mk-body" v-html="mkHtml" />
    <template #footer>
      <el-button :icon="Download" @click="downloadMarkdown">下载 Markdown</el-button>
      <el-button type="primary" @click="dialogVisible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.doc-card {
  padding: 14px 18px; border-radius: 10px; margin-bottom: 14px;
  max-width: 460px; cursor: pointer; transition: box-shadow .15s;
}
.doc-card:hover { box-shadow: 0 2px 10px rgba(0,0,0,.06); }
.outline { background: var(--primary-bg); border: 1px solid var(--primary-border); }
.ppt { background: var(--success-bg); border: 1px solid var(--success-border); }
.doc-header { display: flex; align-items: center; gap: 8px; }
.doc-title {
  font-weight: 600; font-size: 14px; flex: 1;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.outline .doc-title { color: var(--primary); }
.ppt .doc-title { color: var(--success); }
.card-loading { opacity: .85; }
.card-loader { margin-top: 8px; height: 4px; border-radius: 2px; overflow: hidden; background: var(--border); }
.loader-bar { height: 100%; width: 30%; border-radius: 2px; background: #409eff; animation: loaderSlide 1s infinite ease-in-out; }
@keyframes loaderSlide {
  0% { margin-left: -30%; }
  100% { margin-left: 130%; }
}
.doc-actions { display: flex; gap: 6px; margin-top: 10px; }
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
