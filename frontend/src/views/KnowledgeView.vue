<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import type { UploadFile } from 'element-plus'
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
const dialogVisible = ref(false)
const uploadFiles = ref<File[]>([])
const uploading = ref(false)

onMounted(() => loadFiles())

async function loadFiles() {
  loading.value = true
  try {
    const { data } = await api.get('/knowledge/files', {
      params: { user_id: auth.userId },
    })
    if (data.code === 0) {
      files.value = data.data.items || []
    }
  } finally {
    loading.value = false
  }
}

async function handleUpload() {
  if (uploadFiles.value.length === 0) return
  uploading.value = true
  try {
    const form = new FormData()
    form.append('user_id', String(auth.userId))
    // Default conv for global knowledge files — use 0
    form.append('conversation_id', '0')
    uploadFiles.value.forEach((f) => form.append('files', f))

    const { data } = await api.post('/knowledge/upload', form)
    if (data.code === 0) {
      ElMessage.success(`上传成功 ${data.data.uploaded.length} 个`)
      await loadFiles()
    }
  } catch {
    ElMessage.error('上传失败')
  } finally {
    uploading.value = false
    dialogVisible.value = false
    uploadFiles.value = []
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

function onFileChange(file: UploadFile) {
  if (file.raw) uploadFiles.value.push(file.raw)
  return false
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
      <el-button type="primary" :icon="UploadFilled" @click="dialogVisible = true">
        上传文件
      </el-button>
    </div>

    <el-skeleton :loading="loading" :count="4" animated />
    <EmptyState v-if="!loading && files.length === 0" description="暂无文件，点击上传" />
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

    <!-- Upload dialog -->
    <el-dialog v-model="dialogVisible" title="上传知识文件" width="500px">
      <el-upload
        drag
        multiple
        :auto-upload="false"
        :on-change="onFileChange as any"
        :file-list="[]"
      >
        <el-icon :size="48"><UploadFilled /></el-icon>
        <div>拖拽文件到此处或点击上传</div>
        <template #tip>
          <div style="margin-top:8px;font-size:12px;color:#909399">
            支持 PDF、Word、Excel、CSV、Markdown、TXT
          </div>
        </template>
      </el-upload>
      <div v-if="uploadFiles.length" style="margin-top:12px">
        <el-tag v-for="(f, i) in uploadFiles" :key="i" style="margin-right:8px" closable
          @close="uploadFiles.splice(i, 1)">
          {{ f.name }}
        </el-tag>
      </div>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploading" :disabled="uploadFiles.length === 0"
          @click="handleUpload">
          开始上传
        </el-button>
      </template>
    </el-dialog>
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
  align-items: center;
  margin-bottom: 24px;
}
</style>
