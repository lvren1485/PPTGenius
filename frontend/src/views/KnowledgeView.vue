<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api/client'
import { useAuthStore } from '../stores/auth'
import EmptyState from '../components/common/EmptyState.vue'

interface KFile {
  id: number | null
  conversation_id: number | null
  filename: string
  file_type: string
  file_size: number | null
  chunk_count: number | null
  source_type: string | null
  status: string | null
  created_at: string
}

const auth = useAuthStore()
const files = ref<KFile[]>([])
const loading = ref(true)

onMounted(() => loadFiles())

async function loadFiles() {
  loading.value = true
  try {
    const { data } = await api.get('/knowledge/files', {
      params: { user_id: auth.userId },
    })
    if (data.code === 0) files.value = data.data.items || []
  } finally {
    loading.value = false
  }
}

async function handleDelete(id: number) {
  try {
    await ElMessageBox.confirm('确定删除该文件？', '确认', { type: 'warning' })
    await api.delete(`/knowledge/files/${id}`)
    ElMessage.success('已删除')
    await loadFiles()
  } catch { /* cancelled */ }
}

function formatSize(b: number | null) {
  if (!b) return ''
  if (b < 1024) return `${b} B`
  return `${(b / 1024).toFixed(1)} KB`
}
</script>

<template>
  <div class="knowledge-page">
    <div class="kp-header">
      <h2>知识库</h2>
      <span class="kp-hint">文件上传请在对话页面中进行</span>
    </div>

    <el-skeleton :loading="loading" :count="4" animated />
    <EmptyState v-if="!loading && files.length === 0" description="暂无文件，前往对话页面上传" />
    <el-table v-if="!loading && files.length > 0" :data="files" stripe>
      <el-table-column prop="filename" label="文件名" min-width="180" />
      <el-table-column prop="file_type" label="类型" width="80" />
      <el-table-column label="大小" width="100">
        <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag size="small" :type="row.status === 'indexed' ? 'success' : 'info'">
            {{ row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="chunk_count" label="Chunks" width="80" />
      <el-table-column label="上传时间" width="110">
        <template #default="{ row }">
          {{ new Date(row.created_at).toLocaleDateString('zh-CN') }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="80" fixed="right">
        <template #default="{ row }">
          <el-popconfirm title="确定删除？" @confirm="handleDelete(row.id!)">
            <template #reference>
              <el-button link type="danger" size="small">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.knowledge-page {
  max-width: 900px;
  margin: 0 auto;
  padding: 24px;
}
.kp-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 24px;
}
.kp-hint {
  color: #909399;
  font-size: 13px;
}
</style>
