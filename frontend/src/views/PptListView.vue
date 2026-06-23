<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api/client'
import { useAuthStore } from '../stores/auth'
import ListItemCard from '../components/common/ListItemCard.vue'

interface Ppt {
  id: number; outline_id: number | null; title: string | null; status: string
  version: number; outline_version: number
  slide_count: number | null; created_at: string | null
}

const auth = useAuthStore()
const ppts = ref<Ppt[]>([])
const loading = ref(true)
const downloadingId = ref(0)

onMounted(async () => {
  try {
    const resp = await api.get('/presentations', { params: { user_id: auth.userId } })
    ppts.value = resp.data?.data?.items ?? []
  } finally { loading.value = false }
})

async function download(id: number, e: Event) {
  downloadingId.value = id
  try {
    const { data } = await api.get(`/ppt/${id}/snapshots`)
    const snaps = data.data?.snapshots || []
    if (snaps.length === 0) { ElMessage.warning('暂无快照可下载'); return }
    const latest = snaps.reduce((a: any, b: any) => a.version > b.version ? a : b)
    const resp = await api.get(`/export/presentation/${latest.id}/content`)
    if (resp.data.code === 0) {
      const byteChars = atob(resp.data.data.content)
      const byteNums = new Array(byteChars.length)
      for (let i = 0; i < byteChars.length; i++) byteNums[i] = byteChars.charCodeAt(i)
      const blob = new Blob([new Uint8Array(byteNums)], { type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = resp.data.data.filename || `ppt_${id}.pptx`; a.click()
      URL.revokeObjectURL(url)
    }
  } catch { ElMessage.error('下载失败') }
  finally { downloadingId.value = 0 }
}

function cardMeta(p: Ppt): string[] { return [`v${p.version}`, `${p.slide_count ?? 0} 页`] }
function cardTags(p: Ppt) { return [{ label: p.status, type: p.status === 'completed' ? 'success' : 'warning' }] }
function cardDate(p: Ppt) { return p.created_at ? new Date(p.created_at).toLocaleDateString('zh-CN') : '' }
</script>

<template>
  <div class="lp">
    <h2 class="lp-title">PPT 列表</h2>
    <p class="lp-sub">共 {{ ppts.length }} 个 PPT</p>
    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="ppts.length === 0" class="empty">暂无 PPT</div>
    <div v-else class="cards">
      <ListItemCard
        v-for="p in ppts" :key="p.id"
        :title="p.title || `PPT #${p.id}`"
        :meta="cardMeta(p)"
        :tags="cardTags(p)"
        :date="cardDate(p)"
        :to="`/ppt/${p.id}`"
        :downloading="downloadingId === p.id"
        @download="download(p.id, $event)"
      />
    </div>
  </div>
</template>

<style scoped>
.lp { max-width: 860px; margin: 0 auto; padding: 40px 24px; }
.lp-title { font-size: 22px; margin-bottom: 6px; }
.lp-sub { color: var(--text-secondary); font-size: 15px; margin-bottom: 28px; }
.loading, .empty { text-align: center; padding: 60px 0; color: #909399; }
.cards { display: flex; flex-direction: column; gap: 10px; }
</style>
