<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api/client'
import { useAuthStore } from '../stores/auth'

interface Outline {
  id: number; title: string; status: string
  eval_score: number | null; version: number; slide_count: number | null
  created_at: string
}

const router = useRouter()
const auth = useAuthStore()
const outlines = ref<Outline[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    const resp = await api.get('/outlines', { params: { user_id: auth.userId } })
    outlines.value = resp.data?.data?.items ?? []
  } finally { loading.value = false }
})
</script>

<template>
  <div class="lp">
    <h2>大纲列表 ({{ outlines.length }})</h2>
    <p v-if="loading">加载中...</p>
    <p v-else-if="outlines.length === 0">暂无大纲</p>
    <div v-else v-for="o in outlines" :key="o.id" class="card" @click="router.push('/outline/' + o.id)">
      <strong>{{ o.title || '未命名' }}</strong>
      <span>v{{ o.version }} · {{ o.slide_count ?? 0 }}页 · {{ o.eval_score?.toFixed(2) ?? '-' }}</span>
      <span class="date">{{ new Date(o.created_at).toLocaleDateString('zh-CN') }}</span>
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
