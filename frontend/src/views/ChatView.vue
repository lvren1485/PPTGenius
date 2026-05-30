<script setup lang="ts">
import { ref, onMounted, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api/client'
import { useAuthStore } from '../stores/auth'
import { streamChat } from '../api/sse'
import MessageBubble from '../components/chat/MessageBubble.vue'
import FileCard from '../components/chat/FileCard.vue'
import ImageCard from '../components/chat/ImageCard.vue'
import OutlineCard from '../components/chat/OutlineCard.vue'
import PptCard from '../components/chat/PptCard.vue'
import ChatInput from '../components/chat/ChatInput.vue'
import SseStatus from '../components/chat/SseStatus.vue'

interface MsgItem {
  id: number
  idx: number
  role: string
  content: string
  content_type: string | null
  estimated_cost: number | null
  created_at: string
}

interface SseState {
  phase: string
  step: string
  detail: string
  pct: number
}

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const convId = Number(route.params.id)

const messages = ref<MsgItem[]>([])
const sse = ref<SseState>({ phase: '', step: '', detail: '', pct: 0 })
const loading = ref(false)

const convTitle = ref('')

onMounted(async () => {
  await loadConversation()
  const msg = route.query.msg as string
  if (msg) {
    router.replace({ query: {} })
    await sendMessage(msg)
    await loadConversation()
  }
})

async function loadConversation() {
  try {
    const { data } = await api.get(`/conversations/${convId}`)
    if (data.code === 0) {
      messages.value = data.data.messages || []
      convTitle.value = data.data.title || ''
    }
  } catch {
    ElMessage.error('加载会话失败')
  }
}

async function sendMessage(text: string) {

  messages.value.push({
    id: 0, idx: messages.value.length + 1,
    role: 'user', content: text, content_type: 'text',
    estimated_cost: null, created_at: new Date().toISOString(),
  })
  await nextTick()
  scrollBottom()

  sse.value = { phase: '', step: '', detail: '', pct: 0 }
  loading.value = true

  try {
    for await (const evt of streamChat(convId, text)) {
      handleSseEvent(evt)
    }
  } catch (e: any) {
    ElMessage.error(e.message || '请求失败')
  } finally {
    loading.value = false
    sse.value = { phase: '', step: '', detail: '', pct: 0 }
  }

  await loadConversation()
  scrollBottom()
}

function handleSseEvent(evt: { event: string; data: Record<string, any> }) {
  const d = evt.data
  switch (evt.event) {
    case 'phase':
      sse.value = { ...sse.value, phase: d.phase || '', detail: d.message || '' }
      break
    case 'progress':
      sse.value = {
        phase: '',
        step: d.step || '',
        detail: d.detail || '',
        pct: d.pct || 0,
      }
      break
    case 'outline':
      // Insert outline card
      messages.value.push({
        id: 0, idx: messages.value.length + 1,
        role: 'assistant', content: JSON.stringify(d),
        content_type: 'outline', estimated_cost: null,
        created_at: new Date().toISOString(),
      })
      scrollBottom()
      break
    case 'ppt_done':
    case 'ppt_ready':
      messages.value.push({
        id: 0, idx: messages.value.length + 1,
        role: 'assistant', content: JSON.stringify(d),
        content_type: 'ppt', estimated_cost: null,
        created_at: new Date().toISOString(),
      })
      scrollBottom()
      break
    case 'knowledge':
      // Knowledge sources — log only
      break
    case 'error':
      ElMessage.error(d.message || '执行出错')
      break
  }
}

async function handleUpload(files: File[]) {
  const form = new FormData()
  form.append('user_id', String(auth.userId))
  form.append('conversation_id', String(convId))
  files.forEach((f) => form.append('files', f))

  try {
    const { data } = await api.post('/knowledge/upload', form)
    if (data.code === 0) {
      ElMessage.success(`已上传 ${data.data.uploaded.length} 个文件`)
      await loadConversation()
    }
  } catch {
    ElMessage.error('上传失败')
  }
}

function scrollBottom() {
  nextTick(() => {
    const el = document.getElementById('msg-container')
    if (el) el.scrollTop = el.scrollHeight
  })
}

function renderMsg(msg: MsgItem) {
  if (msg.content_type === 'file') return 'file'
  if (msg.content_type === 'image') return 'image'
  if (msg.content_type === 'outline') return 'outline'
  if (msg.content_type === 'ppt') return 'ppt'
  return 'text'
}
</script>

<template>
  <div class="chat-page">
    <div class="chat-header">
      <el-button text @click="router.push('/')">← 返回</el-button>
      <span class="chat-title">{{ convTitle || '新会话' }}</span>
    </div>

    <div class="msg-container" id="msg-container">
      <template v-for="msg in messages" :key="msg.id || msg.idx">
        <MessageBubble
          v-if="renderMsg(msg) === 'text'"
          :role="msg.role"
          :content="msg.content"
          :content_type="msg.content_type"
          :created-at="msg.created_at"
        />
        <FileCard
          v-else-if="renderMsg(msg) === 'file'"
          :content="msg.content"
          :created-at="msg.created_at"
        />
        <ImageCard
          v-else-if="renderMsg(msg) === 'image'"
          :content="msg.content"
          :created-at="msg.created_at"
        />
        <OutlineCard
          v-else-if="renderMsg(msg) === 'outline'"
          :outline-data="JSON.parse(msg.content)"
        />
        <PptCard
          v-else-if="renderMsg(msg) === 'ppt'"
          :ppt-data="JSON.parse(msg.content)"
        />
      </template>
    </div>

    <SseStatus
      v-if="sse.phase || sse.step"
      :phase="sse.phase"
      :step="sse.step"
      :detail="sse.detail"
      :pct="sse.pct"
    />

    <ChatInput @send="sendMessage" @upload="handleUpload" />
  </div>
</template>

<style scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 56px);
  max-width: 900px;
  margin: 0 auto;
}
.chat-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 24px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
}
.chat-title {
  font-weight: 600;
}
.msg-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
}
</style>
