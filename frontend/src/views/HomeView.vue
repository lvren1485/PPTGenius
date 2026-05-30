<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ChatDotRound } from '@element-plus/icons-vue'
import api from '../api/client'
import { useAuthStore } from '../stores/auth'
import EmptyState from '../components/common/EmptyState.vue'
import type { SseEvent } from '../api/sse'
import { streamChat } from '../api/sse'

interface ConvItem {
  id: number
  title: string
  status: string
  current_phase: string | null
  message_count: number
  estimated_cost: number | null
  created_at: string
  updated_at: string
}

const router = useRouter()
const auth = useAuthStore()
const convs = ref<ConvItem[]>([])
const loading = ref(false)
const inputMessage = ref('')
const sending = ref(false)

const phaseLabels: Record<string, string> = {
  chat: '对话中',
  outline: '大纲中',
  ppt: 'PPT生成中',
  completed: '已完成',
}

onMounted(() => loadConvs())

async function loadConvs() {
  loading.value = true
  try {
    const { data } = await api.get('/conversations', { params: { user_id: auth.userId } })
    if (data.code === 0) convs.value = data.data.items || []
  } finally {
    loading.value = false
  }
}

async function handleSend() {
  const msg = inputMessage.value.trim()
  if (!msg) return
  sending.value = true
  try {
    // Step 1: Create conversation first
    const { data: convData } = await api.post('/conversations', {
      user_id: auth.userId,
      title: msg.slice(0, 50),
    })
    const convId = convData.data.id

    // Step 2: Navigate to chat page
    await router.push({ name: 'Chat', params: { id: String(convId) }, query: { msg } })
  } catch (e: any) {
    ElMessage.error('发送失败')
  } finally {
    sending.value = false
  }
}

function openChat(id: number) {
  router.push(`/chat/${id}`)
}

function formatDate(d: string) {
  return new Date(d).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

function goToChat() {
  // Focus on input area
}
</script>

<template>
  <div class="home-page">
    <div class="home-content">
      <!-- Chat launcher -->
      <div class="launcher-card">
        <h2>开始创建 PPT</h2>
        <p class="launcher-hint">描述你的需求，AI 将为你生成大纲和 PPT</p>
        <div class="launcher-input">
          <el-input
            v-model="inputMessage"
            placeholder="例如：做一个Python数据分析的PPT..."
            :rows="2"
            type="textarea"
            @keydown.enter.exact.prevent="handleSend"
          />
          <el-button
            type="primary"
            :loading="sending"
            :disabled="!inputMessage.trim()"
            @click="handleSend"
          >
            发送
          </el-button>
        </div>
      </div>

      <!-- Conversation list -->
      <div class="conv-section">
        <h3>历史会话</h3>
        <el-skeleton :loading="loading" :count="3" animated />
        <EmptyState v-if="!loading && convs.length === 0" description="暂无会话，输入上方内容开始" />
        <div v-if="!loading && convs.length > 0" class="conv-list">
          <div
            v-for="c in convs"
            :key="c.id"
            class="conv-item"
            @click="openChat(c.id)"
          >
            <div class="conv-main">
              <span class="conv-title">{{ c.title || '未命名会话' }}</span>
              <span class="conv-meta">
                {{ c.message_count }} 条消息
                <el-tag size="small" :type="c.status === 'active' ? 'success' : 'info'">
                  {{ c.status === 'active' ? '活跃' : c.status }}
                </el-tag>
              </span>
            </div>
            <div class="conv-sub">
              <span>{{ c.current_phase ? phaseLabels[c.current_phase] || c.current_phase : '' }}</span>
              <span>{{ c.estimated_cost ? `¥${c.estimated_cost.toFixed(4)}` : '' }}</span>
              <span>{{ formatDate(c.updated_at) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.home-page {
  max-width: 800px;
  margin: 0 auto;
  padding: 40px 24px;
}
.launcher-card {
  background: #fff;
  border-radius: 12px;
  padding: 32px;
  margin-bottom: 32px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, .06);
}
.launcher-card h2 {
  font-size: 22px;
  margin-bottom: 8px;
}
.launcher-hint {
  color: #909399;
  margin-bottom: 20px;
  font-size: 14px;
}
.launcher-input {
  display: flex;
  gap: 12px;
  align-items: flex-end;
}
.launcher-input :deep(.el-textarea) {
  flex: 1;
}
.conv-section h3 {
  margin-bottom: 16px;
  font-size: 16px;
  color: #606266;
}
.conv-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.conv-item {
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
  cursor: pointer;
  transition: box-shadow .2s;
}
.conv-item:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, .1);
}
.conv-main {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.conv-title {
  font-weight: 600;
}
.conv-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #909399;
}
.conv-sub {
  display: flex;
  gap: 16px;
  font-size: 13px;
  color: #c0c4cc;
}
</style>
