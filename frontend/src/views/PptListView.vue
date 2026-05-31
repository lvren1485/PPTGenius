<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api/client'
import { useAuthStore } from '../stores/auth'

interface Ppt {
  id: number; status: string; slide_count: number | null
  file_path: string; file_size: number | null; created_at: string | null
}

const router = useRouter()
const auth = useAuthStore()
const ppts = ref<Ppt[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    const resp = await api.get('/presentations', { params: { user_id: auth.userId } })
    ppts.value = resp.data?.data?.items ?? []
  } finally { loading.value = false }
})

function download(id: number, e: Event) {
  e.stopPropagation()
  window.open('/api/ppt/' + id + '/download', '_blank')
}
</script>

<template>
  <div class="lp">
    <h2>PPT 列表 ({{ ppts.length }})</h2>
    <p v-if="loading">加载中...</p>
    <p v-else-if="ppts.length === 0">暂无 PPT</p>
    <div v-else v-for="p in ppts" :key="p.id" class="card" @click="router.push('/ppt/' + p.id)">
      <strong>{{ p.file_path.split('/').pop() }}</strong>
      <span>{{ p.status }} · {{ p.slide_count ?? 0 }}页</span>
      <button @click="download(p.id, $event)">下载</button>
      <span class="date">{{ p.created_at ? new Date(p.created_at).toLocaleDateString('zh-CN') : '' }}</span>
    </div>
  </div>
</template>

<style scoped>
.lp { max-width:800px; margin:0 auto; padding:24px; }
.card { background:#fff; padding:16px; margin-bottom:10px; border-radius:8px; cursor:pointer;
  display:flex; align-items:center; gap:16px; }
.card:hover { box-shadow:0 2px 8px rgba(0,0,0,.1); }
.date { margin-left:auto; color:#c0c4cc; font-size:13px; }
</style>
