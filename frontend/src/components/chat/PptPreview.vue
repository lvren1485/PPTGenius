<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { Download } from '@element-plus/icons-vue'

const props = defineProps<{ snapId: number; visible: boolean }>()
const emit = defineEmits<{ close: [] }>()

const containerRef = ref<HTMLDivElement | null>(null)
const loading = ref(false)
const error = ref('')
const pptBuffer = ref<ArrayBuffer | null>(null)
const previewer = ref<any>(null)

watch(() => props.visible, async (v) => {
  if (!v) return
  await loadPptx()
})

async function loadPptx() {
  if (!props.snapId) return
  loading.value = true; error.value = ''; pptBuffer.value = null
  try {
    const { default: api } = await import('../../api/client')
    const { data } = await api.get(`/export/presentation/${props.snapId}/content`)
    if (data.code === 0) {
      // Decode base64 to ArrayBuffer using fetch
      const resp = await fetch(`data:application/octet-stream;base64,${data.data.content}`)
      pptBuffer.value = await resp.arrayBuffer()
      loading.value = false
      await nextTick()
      await new Promise(r => setTimeout(r, 300))
      await nextTick()
      await renderPptx()
    }
  } catch { error.value = '加载失败'; loading.value = false }
}

async function renderPptx() {
  if (!containerRef.value || !pptBuffer.value) return
  try {
    const { init } = await import('pptx-preview')
    // Always create fresh previewer — destroy-on-close kills old DOM
    previewer.value = init(containerRef.value, { width: 1100, height: 618 })
    previewer.value.preview(pptBuffer.value)
  } catch { error.value = '渲染失败' }
}

function download() {
  if (!pptBuffer.value) return
  const blob = new Blob([pptBuffer.value], { type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a'); a.href = url
  a.download = `presentation_v${props.snapId}.pptx`; a.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <el-dialog :modelValue="visible" @update:modelValue="$emit('close')" title="PPT 预览" width="90%" top="2vh" destroy-on-close class="ppt-preview-dialog">
    <div v-if="loading" style="text-align:center;padding:60px 0">
      <div class="spinner" /><p style="margin-top:16px;color:var(--text-secondary)">正在生成预览，请稍候...</p>
    </div>
    <div v-else-if="error" style="text-align:center;padding:40px 0;color:var(--danger)">{{ error }}</div>
    <div v-else ref="containerRef" class="ppt-container" />
    <template #footer>
      <el-button :icon="Download" type="primary" @click="download" :disabled="!pptBuffer">下载 PPTX</el-button>
      <el-button @click="$emit('close')">关闭</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.ppt-container {
  width: 1060px; max-width: 100%; height: calc(90vh - 120px); margin: 0 auto;
  overflow-x: auto; overflow-y: hidden;
}
.ppt-container::-webkit-scrollbar { display: none; }
.ppt-container { scrollbar-width: none; }
.spinner { width: 40px; height: 40px; margin: 0 auto; border: 3px solid var(--border); border-top-color: var(--primary); border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>

<style>
.ppt-preview-dialog .el-dialog__body { padding: 8px 20px; overflow: hidden; }
.ppt-preview-dialog .el-dialog__header { padding: 12px 20px 4px; margin: 0; }
.ppt-preview-dialog .el-dialog__footer { padding: 4px 20px 12px; }
</style>
