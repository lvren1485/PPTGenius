<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { Download, Document } from '@element-plus/icons-vue'
import { marked } from 'marked'
import api from '../../api/client'

const props = defineProps<{
  docType: string         // "outline" | "presentation"
  metadata: {
    outline_id?: number
    presentation_id?: number
    title?: string
  }
  content: string         // title (from SSE) or snapshot id string (from DB)
}>()

const router = useRouter()
const expanded = ref(false)
const mkHtml = ref('')
const mkFilename = ref('')
const loading = ref(false)

const title = computed(() => props.metadata.title || props.content || '')
const snapId = computed(() => {
  // From SSE: metadata has the snapshot id
  if (props.metadata.outline_id) return props.metadata.outline_id
  if (props.metadata.presentation_id) return props.metadata.presentation_id
  // From DB: content might be the snapshot id
  const n = Number(props.content)
  return isNaN(n) ? 0 : n
})

const isOutline = computed(() => props.docType === 'outline')

async function togglePreview() {
  if (expanded.value) {
    expanded.value = false
    return
  }
  if (isOutline.value && mkHtml.value) {
    expanded.value = true
    return
  }
  if (!isOutline.value) {
    // PPT: navigate to snapshot detail
    if (snapId.value > 0) router.push(`/snapshot/${snapId.value}`)
    return
  }
  // Outline: fetch markdown content
  await fetchMarkdown()
}

async function fetchMarkdown() {
  if (!snapId.value) return
  loading.value = true
  try {
    const { data } = await api.get(`/export/outline/${snapId.value}/content`)
    if (data.code === 0) {
      mkHtml.value = marked(data.data.content) as string
      mkFilename.value = data.data.filename
      expanded.value = true
    }
  } catch {
    // ignore
  } finally {
    loading.value = false
  }
}

function downloadMarkdown() {
  const txt = document.querySelector('.mk-body')?.textContent || mkHtml.value
  const blob = new Blob([txt], { type: 'text/markdown; charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = mkFilename.value || `outline_${snapId.value}.md`
  a.click()
  URL.revokeObjectURL(url)
}

async function downloadPptx() {
  if (!snapId.value) return
  try {
    const { data } = await api.get(`/export/presentation/${snapId.value}/content`)
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
      a.download = data.data.filename || `presentation_${snapId.value}.pptx`
      a.click()
      URL.revokeObjectURL(url)
    }
  } catch {
    // ignore
  }
}
</script>

<template>
  <div class="doc-card" :class="isOutline ? 'outline' : 'ppt'" @click="togglePreview">
    <div class="doc-header">
      <el-icon :size="18"><Document /></el-icon>
      <span class="doc-title">{{ isOutline ? '大纲' : 'PPT' }}：{{ title }}</span>
      <el-tag size="small" :type="isOutline ? 'primary' : 'success'">
        {{ isOutline ? '大纲' : 'PPT' }}
      </el-tag>
    </div>

    <!-- Outline: rendered markdown preview -->
    <div v-if="isOutline && expanded" class="doc-expand mk-body" v-html="mkHtml" @click.stop />
    <div v-if="isOutline && loading" class="doc-expand loading">加载中...</div>

    <!-- Actions -->
    <div class="doc-actions" v-if="snapId > 0" @click.stop>
      <template v-if="isOutline">
        <el-button size="small" text type="primary" :loading="loading" @click="fetchMarkdown">
          {{ expanded ? '刷新预览' : '查看大纲' }}
        </el-button>
        <el-button v-if="expanded" size="small" text :icon="Download" @click="downloadMarkdown">
          下载
        </el-button>
      </template>
      <template v-else>
        <el-button size="small" text type="primary" @click="router.push(`/snapshot/${snapId}`)">
          查看详情
        </el-button>
        <el-button size="small" text :icon="Download" @click="downloadPptx">
          下载 PPTX
        </el-button>
      </template>
    </div>
  </div>
</template>

<style scoped>
.doc-card {
  padding: 14px 18px;
  border-radius: 10px;
  margin-bottom: 14px;
  max-width: 460px;
  cursor: pointer;
  transition: box-shadow .15s;
}
.doc-card:hover {
  box-shadow: 0 2px 10px rgba(0,0,0,.06);
}
.outline { background: #ecf5ff; border: 1px solid #d9ecff; }
.ppt { background: #f0f9eb; border: 1px solid #e1f3d8; }
.doc-header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.doc-title {
  font-weight: 600;
  font-size: 14px;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.outline .doc-title { color: #409eff; }
.ppt .doc-title { color: #67c23a; }
.doc-expand {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fff;
  border-radius: 8px;
  max-height: 400px;
  overflow-y: auto;
  font-size: 13px;
  line-height: 1.7;
  cursor: default;
}
.doc-expand.loading {
  color: #909399;
  text-align: center;
  padding: 20px;
}
.mk-body :deep(h1) { font-size: 18px; margin-top: 0; }
.mk-body :deep(h2) { font-size: 16px; }
.mk-body :deep(h3) { font-size: 14px; }
.mk-body :deep(ul) { padding-left: 18px; }
.doc-actions {
  display: flex;
  gap: 6px;
  margin-top: 10px;
}
</style>
