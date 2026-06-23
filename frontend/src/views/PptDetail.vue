<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Clock } from '@element-plus/icons-vue'
import api from '../api/client'
import EmptyState from '../components/common/EmptyState.vue'
import PptPreview from '../components/chat/PptPreview.vue'

interface SnapItem { id: number; version: number; created_at: string }

const route = useRoute(); const router = useRouter()
const pptId = Number(route.params.id)
const pres = ref<any>(null)
const loading = ref(true)
const snaps = ref<SnapItem[]>([])
const snapsLoading = ref(false)
const previewSnapId = ref(0)
const previewVisible = ref(false)
const previewTitle = ref('')

onMounted(async () => {
  try {
    const { data } = await api.get(`/ppt/${pptId}`)
    if (data.code === 0) pres.value = data.data
  } catch { ElMessage.error('加载 PPT 失败') }
  finally { loading.value = false }
  loadSnapshots()
})

async function loadSnapshots() {
  snapsLoading.value = true
  try { const { data } = await api.get(`/ppt/${pptId}/snapshots`); if (data.code === 0) snaps.value = data.data.snapshots || [] }
  catch { /* */ }
  finally { snapsLoading.value = false }
}

function openPreview(snapId: number, ver: number) {
  previewSnapId.value = snapId
  previewTitle.value = `v${ver}`
  previewVisible.value = true
}

</script>

<template>
  <div class="ppt-page">
    <div class="pp-header">
      <el-button text @click="router.back()">← 返回</el-button>
      <h2 v-if="pres">PPT 预览</h2>
      <div v-if="pres" class="pp-meta">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="状态"><el-tag :type="pres.status==='completed'?'success':'warning'">{{ pres.status }}</el-tag></el-descriptions-item>
          <el-descriptions-item label="页数">{{ pres.slide_count || 0 }}</el-descriptions-item>
          <el-descriptions-item label="版本">v{{ pres.version }}</el-descriptions-item>
          <el-descriptions-item label="大纲版本">v{{ pres.outline_version }}</el-descriptions-item>
          <el-descriptions-item label="样式">{{ pres.style_name || ('#'+pres.style_id) || '默认' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ pres.created_at ? new Date(pres.created_at).toLocaleString('zh-CN') : '' }}</el-descriptions-item>
        </el-descriptions>
      </div>
    </div>

    <div class="snap-section">
      <h3 class="section-title">历史快照</h3>
      <div v-if="snapsLoading" class="snap-loading">加载中...</div>
      <EmptyState v-else-if="snaps.length===0" description="暂无快照" />
      <div v-else class="snap-cards">
        <div v-for="s in snaps" :key="s.id" class="snap-card" @click="openPreview(s.id, s.version)">
          <el-icon :size="18"><Clock /></el-icon>
          <span class="snap-ver">v{{ s.version }}</span>
          <span class="snap-time">{{ new Date(s.created_at).toLocaleString('zh-CN') }}</span>
          <el-tag size="small" type="success">查看</el-tag>
        </div>
      </div>
    </div>

  </div>

  <PptPreview :snap-id="previewSnapId" :visible="previewVisible" @close="previewVisible = false" />
</template>

<style scoped>
.ppt-page { max-width: 900px; margin: 0 auto; padding: 24px; }
.pp-header { margin-bottom: 24px; }
.pp-header h2 { margin: 8px 0 12px; }
.section-title { font-size: 17px; margin: 28px 0 14px; color: var(--text); }
.snap-loading { color: var(--text-secondary); font-size: 13px; padding: 8px 0; }
.snap-cards { display: flex; flex-wrap: wrap; gap: 10px; }
.snap-card { display: flex; align-items: center; gap: 10px; padding: 12px 18px; background: var(--success-bg); border: 1px solid var(--success-border); border-radius: var(--radius); cursor: pointer; transition: box-shadow .15s; }
.snap-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,.06); }
.snap-ver { font-weight: 600; color: var(--success); font-size: 14px; }
.snap-time { font-size: 13px; color: var(--text-secondary); }
</style>
