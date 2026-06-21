<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus, FolderChecked, Delete } from '@element-plus/icons-vue'
import api from '../../api/client'
import { useAuthStore } from '../../stores/auth'

interface ConvItem {
  id: number
  title: string
  status: string
  current_phase: string | null
  message_count: number
  estimated_cost: number | null
  updated_at: string
}

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const convs = ref<ConvItem[]>([])

const activeId = computed(() => {
  const id = Number(route.params.id)
  return isNaN(id) ? 0 : id
})

onMounted(() => loadConvs())

// Reload when route changes (new conv created, archive/delete, etc.)
watch(() => route.path, () => loadConvs())

async function loadConvs() {
  try {
    const { data } = await api.get('/conversations', {
      params: { user_id: auth.userId, status: 'active' },
    })
    if (data.code === 0) convs.value = data.data.items || []
  } catch { /* ignore */ }
}

function createChat() {
  router.push('/')
}

function selectChat(id: number) {
  if (id !== activeId.value) {
    router.push(`/chat/${id}`)
  }
}

async function archiveConv(id: number, e: Event) {
  e.stopPropagation()
  try {
    await ElMessageBox.confirm('确定归档该会话？', '确认归档', { type: 'warning' })
  } catch { return }
  try {
    await api.patch(`/conversations/${id}/archive`)
    convs.value = convs.value.filter(c => c.id !== id)
    ElMessage.success('已归档')
    if (activeId.value === id) router.push('/')
  } catch {
    ElMessage.error('归档失败')
  }
}

async function deleteConv(id: number, e: Event) {
  e.stopPropagation()
  try {
    await ElMessageBox.confirm('确定删除该会话？此操作不可恢复。', '确认删除', { type: 'error', confirmButtonText: '删除', cancelButtonText: '取消' })
  } catch { return }
  try {
    await api.delete(`/conversations/${id}`)
    convs.value = convs.value.filter(c => c.id !== id)
    ElMessage.success('已删除')
    if (activeId.value === id) router.push('/')
  } catch {
    ElMessage.error('删除失败')
  }
}

function formatDate(d: string) {
  return new Date(d).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}
</script>

<template>
  <div class="sidebar">
    <el-button :icon="Plus" @click="createChat" class="new-btn">
      新对话
    </el-button>

    <div class="conv-list">
      <div
        v-for="c in convs"
        :key="c.id"
        class="conv-item"
        :class="{ active: c.id === activeId }"
        @click="selectChat(c.id)"
      >
        <div class="conv-row">
          <div class="conv-title">{{ c.title || '未命名' }}</div>
          <div class="conv-actions">
            <el-button
              :icon="FolderChecked"
              size="small"
              text
              title="归档"
              @click="archiveConv(c.id, $event)"
            />
            <el-button
              :icon="Delete"
              size="small"
              text
              title="删除"
              @click="deleteConv(c.id, $event)"
            />
          </div>
        </div>
        <div class="conv-meta">
          <span>{{ c.message_count }} 条</span>
          <span>{{ formatDate(c.updated_at) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sidebar {
  width: 260px;
  min-width: 260px;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #e8ecf1;
  border-right: 1px solid #e4e7ed;
}
.new-btn {
  margin: 12px;
}
.conv-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 8px 8px;
}
.conv-item {
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 2px;
  transition: background .15s;
}
.conv-item:hover {
  background: #ebeef5;
}
.conv-item.active {
  background: #d9ecff;
}
.conv-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.conv-title {
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
}
.conv-actions {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
  visibility: hidden;
  opacity: 0;
  transition: opacity .15s;
}
.conv-item:hover .conv-actions {
  visibility: visible;
  opacity: 1;
}
.conv-meta {
  display: flex;
  justify-content: space-between;
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
}
</style>
