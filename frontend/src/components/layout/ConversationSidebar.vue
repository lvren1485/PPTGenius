<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Plus } from '@element-plus/icons-vue'
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
const loading = ref(false)

const activeId = computed(() => {
  const id = Number(route.params.id)
  return isNaN(id) ? 0 : id
})

onMounted(() => loadConvs())

async function loadConvs() {
  loading.value = true
  try {
    const { data } = await api.get('/conversations', { params: { user_id: auth.userId } })
    if (data.code === 0) convs.value = data.data.items || []
  } finally { loading.value = false }
}

function createChat() {
  router.push('/')
}

function selectChat(id: number) {
  if (id !== activeId.value) {
    router.push(`/chat/${id}`)
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
        <div class="conv-title">{{ c.title || '未命名' }}</div>
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
.conv-title {
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.conv-meta {
  display: flex;
  justify-content: space-between;
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
}
</style>
