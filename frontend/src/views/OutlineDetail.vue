<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api/client'
import EmptyState from '../components/common/EmptyState.vue'

interface Slide {
  id: number
  slide_index: number
  title: string
  content_json: Record<string, any> | null
  layout_type: string | null
  has_image: boolean | null
  has_chart: boolean | null
  notes: string | null
}

const route = useRoute()
const router = useRouter()
const outlineId = Number(route.params.id)
const outline = ref<any>(null)
const slides = ref<Slide[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    const { data } = await api.get(`/outline/${outlineId}`)
    if (data.code === 0) {
      outline.value = data.data
      slides.value = data.data.slides || []
    }
  } catch {
    ElMessage.error('加载大纲失败')
  } finally {
    loading.value = false
  }
})

function formatContent(c: Record<string, any> | null) {
  if (!c) return ''
  const parts: string[] = []
  if (c.main_points?.length) parts.push('要点: ' + c.main_points.join(' · '))
  if (c.key_data) parts.push('数据: ' + c.key_data)
  if (c.recommended_ppt_format) parts.push('格式: ' + c.recommended_ppt_format)
  if (c.subtitle) parts.push('副标题: ' + c.subtitle)
  return parts.join(' | ')
}
</script>

<template>
  <div class="outline-page">
    <div class="op-header">
      <el-button text @click="router.back()">← 返回</el-button>
      <h2 v-if="outline">{{ outline.title }}</h2>
      <div v-if="outline" class="op-meta">
        <el-tag>v{{ outline.version }}</el-tag>
        <el-tag type="warning" v-if="outline.eval_score != null">
          评分 {{ outline.eval_score }}
        </el-tag>
        <span>{{ slides.length }} 页</span>
      </div>
    </div>

    <el-skeleton :loading="loading" :count="4" animated />
    <EmptyState v-if="!loading && slides.length === 0" description="暂无内容" />
    <div v-if="!loading" class="slide-list">
      <el-card v-for="s in slides" :key="s.id" class="slide-item" shadow="hover">
        <div class="slide-header">
          <span class="slide-num">Slide {{ s.slide_index + 1 }}</span>
          <span class="slide-title-text">{{ s.title }}</span>
          <el-tag size="small">{{ s.layout_type }}</el-tag>
          <el-tag v-if="s.has_image" size="small" type="success">有图片</el-tag>
          <el-tag v-if="s.has_chart" size="small" type="warning">有图表</el-tag>
        </div>
        <div v-if="formatContent(s.content_json)" class="slide-content">
          {{ formatContent(s.content_json) }}
        </div>
        <div v-if="s.notes" class="slide-notes">备注: {{ s.notes }}</div>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.outline-page {
  max-width: 800px;
  margin: 0 auto;
  padding: 24px;
}
.op-header {
  margin-bottom: 24px;
}
.op-header h2 {
  margin: 8px 0;
}
.op-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #909399;
}
.slide-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.slide-item {
  padding: 4px 0;
}
.slide-header {
  display: flex;
  align-items: center;
  gap: 10px;
}
.slide-num {
  font-weight: 700;
  color: #409eff;
  min-width: 70px;
}
.slide-title-text {
  font-weight: 600;
  flex: 1;
}
.slide-content {
  margin-top: 10px;
  font-size: 14px;
  color: #606266;
}
.slide-notes {
  margin-top: 8px;
  font-size: 13px;
  color: #c0c4cc;
}
</style>
