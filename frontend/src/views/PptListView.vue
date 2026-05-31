<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api/client'
import { useAuthStore } from '../stores/auth'
import EmptyState from '../components/common/EmptyState.vue'

interface Ppt {
  id: number
  conversation_id: number
  outline_id: number | null
  status: string
  slide_count: number | null
  file_path: string
  file_size: number | null
  created_at: string | null
  updated_at: string | null
}

const router = useRouter()
const auth = useAuthStore()
const ppts = ref<Ppt[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    const { data } = await api.get('/presentations', { params: { user_id: auth.userId } })
    if (data.code === 0) ppts.value = data.data.items || []
  } finally {
    loading.value = false
  }
})

function goDetail(id: number) {
  router.push(`/ppt/${id}`)
}
function download(id: number, e: Event) {
  e.stopPropagation()
  window.open(`/api/ppt/${id}/download`, '_blank')
}
function formatSize(b: number | null) {
  if (!b) return ''
  if (b < 1024) return `${b} B`
  return `${(b / 1024).toFixed(1)} KB`
}
</script>

<template>
  <div class="list-page">
    <div class="lp-header">
      <h2>全部 PPT</h2>
      <span class="lp-count">共 {{ ppts.length }} 个</span>
    </div>

    <el-skeleton :loading="loading" :count="4" animated />
    <EmptyState v-if="!loading && ppts.length === 0" description="暂无 PPT" />
    <div v-if="!loading" class="list-cards">
      <el-card
        v-for="p in ppts"
        :key="p.id"
        class="list-card"
        shadow="hover"
        @click="goDetail(p.id)"
      >
        <div class="card-row">
          <span class="card-title">{{ p.file_path.split('/').pop() || p.file_path }}</span>
          <div class="card-tags">
            <el-tag size="small" :type="p.status === 'completed' ? 'success' : 'warning'">
              {{ p.status }}
            </el-tag>
            <el-tag v-if="p.slide_count" size="small">{{ p.slide_count }} 页</el-tag>
          </div>
        </div>
        <div class="card-sub">
          <span>{{ formatSize(p.file_size) }}</span>
          <span v-if="p.created_at">{{ new Date(p.created_at).toLocaleDateString('zh-CN') }}</span>
          <el-button link type="primary" size="small" @click="download(p.id, $event)">
            下载
          </el-button>
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
  align-items: center;
  gap: 16px;
  margin-top: 8px;
  font-size: 13px;
  color: #c0c4cc;
}
</style>
