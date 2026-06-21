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
const expandedSnaps = ref<number | null>(null)
const snapshots = ref<Record<number, any[]>>({})

onMounted(async () => {
  try {
    const resp = await api.get('/outlines', { params: { user_id: auth.userId } })
    outlines.value = resp.data?.data?.items ?? []
  } finally { loading.value = false }
})

async function toggleSnapshots(outlineId: number) {
  if (expandedSnaps.value === outlineId) {
    expandedSnaps.value = null
    return
  }
  expandedSnaps.value = outlineId
  if (!snapshots.value[outlineId]) {
    try {
      const { data } = await api.get(`/export/outline/${outlineId}/snapshots`)
      if (data.code === 0) {
        snapshots.value[outlineId] = data.data.snapshots || []
      }
    } catch {
      snapshots.value[outlineId] = []
    }
  }
}

function viewSnapshot(snapId: number) {
  router.push(`/snapshot/${snapId}`)
}

function formatDate(d: string) {
  return new Date(d).toLocaleString('zh-CN')
}
</script>

<template>
  <div class="lp">
    <h2 class="lp-title">大纲列表</h2>
    <p class="lp-sub">共 {{ outlines.length }} 个大纲</p>

    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="outlines.length === 0" class="empty">暂无大纲</div>

    <div v-else class="cards">
      <div v-for="o in outlines" :key="o.id" class="card-group">
        <div class="card" @click="router.push('/outline/' + o.id)">
          <div class="card-body">
            <strong class="card-title">{{ o.title || '未命名大纲' }}</strong>
            <div class="card-meta">
              <span>v{{ o.version }}</span>
              <span>{{ o.slide_count ?? 0 }} 页</span>
              <span v-if="o.eval_score != null">评分 {{ o.eval_score.toFixed(2) }}</span>
              <el-tag size="small" :type="o.status === 'confirmed' ? 'success' : 'info'">{{ o.status }}</el-tag>
            </div>
          </div>
          <div class="card-right">
            <el-button
              size="small"
              text
              type="primary"
              @click.stop="toggleSnapshots(o.id)"
            >
              {{ expandedSnaps === o.id ? '收起快照' : '查看快照' }}
            </el-button>
            <span class="card-date">{{ new Date(o.created_at).toLocaleDateString('zh-CN') }}</span>
          </div>
        </div>
        <!-- Snapshots dropdown -->
        <div v-if="expandedSnaps === o.id" class="snap-panel">
          <div v-if="!snapshots[o.id]" class="snap-loading">加载中...</div>
          <div v-else-if="snapshots[o.id].length === 0" class="snap-empty">暂无快照</div>
          <div v-else class="snap-list">
            <div
              v-for="s in snapshots[o.id]"
              :key="s.id"
              class="snap-item"
              @click="viewSnapshot(s.id)"
            >
              <span class="snap-ver">快照 v{{ s.version }}</span>
              <span class="snap-time">{{ formatDate(s.created_at) }}</span>
              <el-button link type="primary" size="small">查看</el-button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lp {
  max-width: 860px;
  margin: 0 auto;
  padding: 40px 24px;
}
.lp-title { font-size: 22px; margin-bottom: 6px; }
.lp-sub { color: #909399; font-size: 14px; margin-bottom: 28px; }
.loading, .empty { text-align: center; padding: 60px 0; color: #909399; }
.cards { display: flex; flex-direction: column; gap: 4px; }
.card-group { margin-bottom: 2px; }
.card {
  background: #fff; padding: 20px 24px; border-radius: 10px; cursor: pointer;
  display: flex; align-items: center; justify-content: space-between;
  border: 1px solid #ebeef5; transition: box-shadow .2s, border-color .2s;
}
.card:hover { box-shadow: 0 4px 16px rgba(0,0,0,.08); border-color: #c6e2ff; }
.card-body { display: flex; flex-direction: column; gap: 8px; }
.card-title { font-size: 15px; }
.card-meta { display: flex; align-items: center; gap: 12px; font-size: 13px; color: #909399; }
.card-right { display: flex; align-items: center; gap: 12px; }
.card-date { font-size: 13px; color: #c0c4cc; white-space: nowrap; }
.snap-panel {
  background: #f5f7fa; border: 1px solid #e4e7ed; border-top: none;
  border-radius: 0 0 10px 10px; padding: 12px 24px;
}
.snap-loading, .snap-empty { font-size: 13px; color: #909399; padding: 8px 0; }
.snap-list { display: flex; flex-direction: column; gap: 6px; }
.snap-item {
  display: flex; align-items: center; gap: 16px; padding: 8px 12px;
  background: #fff; border-radius: 6px; cursor: pointer; transition: background .15s;
}
.snap-item:hover { background: #ecf5ff; }
.snap-ver { font-weight: 600; color: #409eff; font-size: 14px; }
.snap-time { flex: 1; font-size: 13px; color: #909399; }
</style>
