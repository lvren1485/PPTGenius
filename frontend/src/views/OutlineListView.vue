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
    <h2 class="lp-title">大纲列表</h2>
    <p class="lp-sub">共 {{ outlines.length }} 个大纲</p>

    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="outlines.length === 0" class="empty">暂无大纲</div>

    <div v-else class="cards">
      <div v-for="o in outlines" :key="o.id" class="card" @click="router.push('/outline/' + o.id)">
        <div class="card-body">
          <strong class="card-title">{{ o.title || '未命名大纲' }}</strong>
          <div class="card-meta">
            <span>v{{ o.version }}</span>
            <span>{{ o.slide_count ?? 0 }} 页</span>
            <span v-if="o.eval_score != null">评分 {{ o.eval_score.toFixed(2) }}</span>
            <el-tag size="small" :type="o.status === 'confirmed' ? 'success' : 'info'">{{ o.status }}</el-tag>
          </div>
        </div>
        <span class="card-date">{{ new Date(o.created_at).toLocaleDateString('zh-CN') }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lp { max-width: 860px; margin: 0 auto; padding: 40px 24px; }
.lp-title { font-size: 22px; margin-bottom: 6px; }
.lp-sub { color: var(--text-secondary); font-size: 15px; margin-bottom: 28px; }
.loading, .empty { text-align: center; padding: 60px 0; color: #909399; }
.cards { display: flex; flex-direction: column; gap: 10px; }
.card {
  background: var(--bg-card); padding: 22px 28px; border-radius: var(--radius); cursor: pointer;
  display: flex; align-items: center; justify-content: space-between;
  border: 1px solid var(--border); transition: box-shadow .2s, border-color .2s;
}
.card:hover { box-shadow: var(--shadow-md); border-color: var(--primary-border); }
.card-body { display: flex; flex-direction: column; gap: 8px; }
.card-title { font-size: 16px; }
.card-meta { display: flex; align-items: center; gap: 12px; font-size: 14px; color: var(--text-secondary); }
.card-date { font-size: 14px; color: var(--text-muted); white-space: nowrap; }
</style>
