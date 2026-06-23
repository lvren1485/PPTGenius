<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api/client'
import { useAuthStore } from '../stores/auth'
import ListItemCard from '../components/common/ListItemCard.vue'

interface Outline {
  id: number; title: string; status: string
  eval_score: number | null; version: number; slide_count: number | null
  created_at: string
}

const auth = useAuthStore()
const outlines = ref<Outline[]>([])
const loading = ref(true)
const downloadingId = ref(0)

onMounted(async () => {
  try {
    const resp = await api.get('/outlines', { params: { user_id: auth.userId } })
    outlines.value = resp.data?.data?.items ?? []
  } finally { loading.value = false }
})

async function download(id: number, e: Event) {
  downloadingId.value = id
  try {
    const { data } = await api.get(`/export/outline-snapshots/${id}`)
    const snaps = data.data?.snapshots || []
    if (snaps.length === 0) { ElMessage.warning('暂无快照可下载'); return }
    const latest = snaps.reduce((a: any, b: any) => a.version > b.version ? a : b)
    const resp = await api.get(`/export/outline/${latest.id}/content`)
    if (resp.data.code === 0) {
      const blob = new Blob([resp.data.data.content], { type: 'text/markdown; charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = resp.data.data.filename || `outline_v${latest.version}.md`; a.click()
      URL.revokeObjectURL(url)
    }
  } catch { ElMessage.error('下载失败') }
  finally { downloadingId.value = 0 }
}

function cardMeta(o: Outline): string[] {
  const m = [`v${o.version}`, `${o.slide_count ?? 0} 页`]
  if (o.eval_score != null) m.push(`评分 ${o.eval_score.toFixed(2)}`)
  return m
}
function cardTags(o: Outline) { return [{ label: o.status, type: o.status === 'completed' || o.status === 'confirmed' ? 'success' : 'warning' }] }
function cardDate(o: Outline) { return new Date(o.created_at).toLocaleDateString('zh-CN') }
</script>

<template>
  <div class="lp">
    <h2 class="lp-title">大纲列表</h2>
    <p class="lp-sub">共 {{ outlines.length }} 个大纲</p>
    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="outlines.length === 0" class="empty">暂无大纲</div>
    <div v-else class="cards">
      <ListItemCard
        v-for="o in outlines" :key="o.id"
        :title="o.title || '未命名大纲'"
        :meta="cardMeta(o)"
        :tags="cardTags(o)"
        :date="cardDate(o)"
        :to="`/outline/${o.id}`"
        :downloading="downloadingId === o.id"
        @download="download(o.id, $event)"
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
