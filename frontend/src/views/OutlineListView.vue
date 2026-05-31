<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api/client'
import { useAuthStore } from '../stores/auth'
import EmptyState from '../components/common/EmptyState.vue'

interface Outline {
  id: number
  title: string
  status: string
  eval_score: number | null
  version: number
  slide_count: number | null
  created_at: string
  updated_at: string
}

const router = useRouter()
const auth = useAuthStore()
const outlines = ref<Outline[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    const { data } = await api.get('/outlines', { params: { user_id: auth.userId } })
    if (data.code === 0) outlines.value = data.data.items || []
  } finally {
    loading.value = false
  }
})

function goDetail(id: number) {
  router.push(`/outline/${id}`)
}
</script>

<template>
  <div class="list-page">
    <div class="lp-header">
      <h2>全部大纲</h2>
      <span class="lp-count">共 {{ outlines.length }} 个</span>
    </div>

    <el-skeleton :loading="loading" :count="4" animated />
    <EmptyState v-if="!loading && outlines.length === 0" description="暂无大纲" />
    <div v-if="!loading" class="list-cards">
      <el-card
        v-for="o in outlines"
        :key="o.id"
        class="list-card"
        shadow="hover"
        @click="goDetail(o.id)"
      >
        <div class="card-row">
          <span class="card-title">{{ o.title || '未命名大纲' }}</span>
          <div class="card-tags">
            <el-tag size="small" :type="o.status === 'confirmed' ? 'success' : 'info'">
              {{ o.status }}
            </el-tag>
            <el-tag size="small">v{{ o.version }}</el-tag>
            <el-tag v-if="o.eval_score != null" size="small" type="warning">
              {{ o.eval_score.toFixed(2) }}
            </el-tag>
          </div>
        </div>
        <div class="card-sub">
          <span>{{ o.slide_count ?? 0 }} 页</span>
          <span>{{ new Date(o.created_at).toLocaleDateString('zh-CN') }}</span>
        </div>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.list-page {
  max-width: 800px;
  margin: 0 auto;
  padding: 24px;
}
.lp-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 20px;
}
.lp-count { color: #909399; }
.list-cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.list-card { cursor: pointer; }
.card-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.card-title { font-weight: 600; }
.card-tags { display: flex; gap: 6px; }
.card-sub {
  display: flex;
  gap: 16px;
  margin-top: 8px;
  font-size: 13px;
  color: #c0c4cc;
}
</style>
