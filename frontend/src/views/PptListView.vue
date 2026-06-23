<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import api from '../api/client'
import { useAuthStore } from '../stores/auth'

interface Ppt {
  id: number; outline_id: number | null; status: string
  version: number; outline_version: number
  slide_count: number | null; created_at: string | null
}

const router = useRouter()
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
  e.stopPropagation()
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
</script>

<template>
  <div class="lp">
    <h2 class="lp-title">PPT 列表</h2>
    <p class="lp-sub">共 {{ ppts.length }} 个 PPT</p>

    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="ppts.length === 0" class="empty">暂无 PPT</div>

    <div v-else class="cards">
      <div v-for="p in ppts" :key="p.id" class="card" @click="router.push('/ppt/' + p.id)">
        <div class="card-body">
          <strong class="card-title">PPT #{{ p.id }}</strong>
          <div class="card-meta">
            <el-tag size="small" :type="p.status === 'completed' ? 'success' : 'warning'">{{ p.status }}</el-tag>
            <span>v{{ p.version }}</span>
            <span>{{ p.slide_count ?? 0 }} 页</span>
          </div>
        </div>
        <div class="card-right">
          <span class="card-date">{{ p.created_at ? new Date(p.created_at).toLocaleDateString('zh-CN') : '' }}</span>
          <el-button :icon="Download" size="small" circle :loading="downloadingId === p.id" @click="download(p.id, $event)" />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lp { max-width: 860px; margin: 0 auto; padding: 40px 24px; }
.lp-title { font-size: 22px; margin-bottom: 6px; }
.lp-sub { color: #909399; font-size: 14px; margin-bottom: 28px; }
.loading, .empty { text-align: center; padding: 60px 0; color: #909399; }
.cards { display: flex; flex-direction: column; gap: 10px; }
.card {
  background: var(--bg-card); padding: 22px 28px; border-radius: var(--radius); cursor: pointer;
  display: flex; align-items: center; justify-content: space-between;
  border: 1px solid #ebeef5; transition: box-shadow .2s, border-color .2s;
}
.card:hover { box-shadow: 0 4px 16px rgba(0,0,0,.08); border-color: #c6e2ff; }
.card-body { display: flex; flex-direction: column; gap: 8px; }
.card-title { font-size: 16px; }
.card-meta { display: flex; align-items: center; gap: 12px; font-size: 14px; color: var(--text-secondary); }
.card-right { display: flex; align-items: center; gap: 16px; }
.card-date { font-size: 14px; color: var(--text-muted); white-space: nowrap; }
</style>
