<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api/client'

const route = useRoute()
const router = useRouter()
const snapId = Number(route.params.id)
const snap = ref<any>(null)
const loading = ref(true)
const showOutline = ref(true)
const showPres = ref(true)

onMounted(async () => {
  try {
    const { data } = await api.get(`/snapshots/${snapId}`)
    if (data.code === 0) snap.value = data.data
  } catch {
    ElMessage.error('加载快照失败')
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="snap-page">
    <div class="snap-header">
      <el-button text @click="router.back()">← 返回</el-button>
      <h2>快照详情</h2>
      <el-descriptions v-if="snap" :column="3" size="small" border>
        <el-descriptions-item label="版本">v{{ snap.version }}</el-descriptions-item>
        <el-descriptions-item label="Presentation ID">{{ snap.presentation_id }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ new Date(snap.created_at).toLocaleString('zh-CN') }}</el-descriptions-item>
      </el-descriptions>
    </div>

    <el-skeleton :loading="loading" :count="3" animated />

    <template v-if="!loading && snap">
      <div class="json-section">
        <div class="json-header" @click="showOutline = !showOutline">
          <span>大纲 (outline_json)</span>
          <el-button link>{{ showOutline ? '折叠' : '展开' }}</el-button>
        </div>
        <pre v-show="showOutline" class="json-block">{{ JSON.stringify(snap.outline_json, null, 2) }}</pre>
      </div>
      <div class="json-section">
        <div class="json-header" @click="showPres = !showPres">
          <span>Presentation (presentation_json)</span>
          <el-button link>{{ showPres ? '折叠' : '展开' }}</el-button>
        </div>
        <pre v-show="showPres" class="json-block">{{ JSON.stringify(snap.presentation_json, null, 2) }}</pre>
      </div>
    </template>
  </div>
</template>

<style scoped>
.snap-page {
  max-width: 900px;
  margin: 0 auto;
  padding: 24px;
}
.snap-header { margin-bottom: 24px; }
.snap-header h2 { margin: 8px 0 12px; }
.json-section { margin-bottom: 20px; }
.json-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 600;
}
.json-block {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 16px;
  border-radius: 6px;
  max-height: 500px;
  overflow: auto;
  font-size: 12px;
  line-height: 1.5;
  margin-top: 8px;
}
</style>
