<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api/client'
import { useAuthStore } from '../stores/auth'
import { streamChat } from '../api/sse'
import ConversationSidebar from '../components/layout/ConversationSidebar.vue'
import MessageBubble from '../components/chat/MessageBubble.vue'
import FileCard from '../components/chat/FileCard.vue'
import ImageCard from '../components/chat/ImageCard.vue'
import DocumentCard from '../components/chat/DocumentCard.vue'
import OutlineCard from '../components/chat/OutlineCard.vue'
import PptCard from '../components/chat/PptCard.vue'
import ChatInput from '../components/chat/ChatInput.vue'
import SseStatus from '../components/chat/SseStatus.vue'

interface MsgItem {
  id: number
  idx: number
  role: string
  content: string
  metadata_json: Record<string, any> | null
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
import type { UploadFile } from 'element-plus'

const router = useRouter()
const auth = useAuthStore()
const convId = computed(() => {
  const id = Number(route.params.id)
  return isNaN(id) ? 0 : id
})

const messages = ref<MsgItem[]>([])
const sse = ref<SseState>({ phase: '', step: '', detail: '', pct: 0 })
const convTitle = ref('')
const startMsg = ref('')

const suggestions = [
  '做一个关于Python数据分析的PPT',
  '介绍人工智能的发展历程',
  '制作一份产品发布会的演示文稿',
  '整理一份毕业论文答辩PPT',
  '制作公司年度总结报告',
]

// Reload when switching conversations
watch(convId, async (id) => {
  if (id > 0) {
    await loadConversation()
    const msg = route.query.msg as string
    if (msg) {
      router.replace({ query: {} })
      await sendMessage(msg)
      await loadConversation()
    }
  } else {
    messages.value = []
    convTitle.value = ''
  }
})

onMounted(async () => {
  if (convId.value > 0) {
    await loadConversation()
    const msg = route.query.msg as string
    if (msg) {
      router.replace({ query: {} })
      await sendMessage(msg)
      await loadConversation()
    }
  }
})

async function loadConversation() {
  try {
    const { data } = await api.get(`/conversations/${convId.value}`)
    if (data.code === 0) {
      messages.value = data.data.messages || []
      convTitle.value = data.data.title || ''
    }
  } catch {
    // ignore
  }
}

async function ensureConversation(title?: string): Promise<number> {
  if (convId.value > 0) return convId.value
  const { data } = await api.post('/conversations', {
    user_id: auth.userId,
    title: title || '新对话',
  })
  const id = data.data.id
  router.replace(`/chat/${id}`)
  return id
}

async function sendMessage(text: string) {
  if (!text.trim()) return
  startMsg.value = ''
  // Lazy-create conversation if needed, auto-title from first 10 chars
  const cid = await ensureConversation(text.slice(0, 10))

  messages.value.push({
    id: 0, idx: messages.value.length + 1,
    role: 'user', content: text, content_type: 'text',
    metadata_json: null, estimated_cost: null, created_at: new Date().toISOString(),
  })
  await nextTick()
  scrollBottom()

  sse.value = { phase: '', step: '', detail: '', pct: 0 }

  try {
    for await (const evt of streamChat(cid, text)) {
      handleSseEvent(evt)
    }
  } catch (e: any) {
    ElMessage.error(e.message || '请求失败')
  } finally {
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
    case 'ppt_done':
    case 'ppt_ready':
      // Handled via 'document' event; ignore old-format inline data
      break
    case 'knowledge':
      // Knowledge sources — log only
      break
    case 'document':
      // Document message (outline/ppt) — same rendering path as history
      messages.value.push({
        id: 0, idx: messages.value.length + 1,
        role: 'document',
        content: d.title || '',
        content_type: d.doc_type,
        metadata_json: d.doc_type === 'outline'
          ? { outline_id: d.outline_id, title: d.title }
          : { presentation_id: d.presentation_id, title: d.title },
        estimated_cost: null,
        created_at: new Date().toISOString(),
      })
      scrollBottom()
      break
    case 'error':
      ElMessage.error(d.message || '执行出错')
      break
  }
}

async function handleUpload(files: File[]) {
  const title = files.length > 0 ? files[0].name.slice(0, 20) : undefined
  const cid = await ensureConversation(title)
  const form = new FormData()
  form.append('user_id', String(auth.userId))
  form.append('conversation_id', String(cid))
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

function onWelcomeUpload(file: UploadFile) {
  if (file.raw) handleUpload([file.raw])
  return false
}

function scrollBottom() {
  nextTick(() => {
    const el = document.getElementById('msg-container')
    if (el) el.scrollTop = el.scrollHeight
  })
}

function renderMsg(msg: MsgItem) {
  if (msg.role === 'document') return 'document'
  if (msg.content_type === 'file') return 'file'
  if (msg.content_type === 'image') return 'image'
  if (msg.content_type === 'outline') return 'outline'
  if (msg.content_type === 'ppt') return 'ppt'
  return 'text'
}
</script>

<template>
  <div class="chat-layout">
    <ConversationSidebar />

    <div class="chat-main">
      <div class="chat-header" v-if="convId">
        <span class="chat-title">{{ convTitle || '新会话' }}</span>
      </div>
      <div class="chat-empty" v-if="!convId">
        <div class="welcome">
          <h2>PPTGenius</h2>
          <p class="welcome-sub">AI 驱动的 PPT 生成助手，输入主题即可开始</p>
          <div class="suggestions">
            <div
              v-for="s in suggestions"
              :key="s"
              class="suggest-item"
              @click="sendMessage(s)"
            >
              {{ s }}
            </div>
          </div>
        </div>
      </div>

      <div class="msg-container" id="msg-container" v-if="convId">
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
          <DocumentCard
            v-else-if="renderMsg(msg) === 'document'"
            :doc-type="msg.content_type || ''"
            :metadata="msg.metadata_json || {}"
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
        v-if="convId && (sse.phase || sse.step)"
        :phase="sse.phase"
        :step="sse.step"
        :detail="sse.detail"
        :pct="sse.pct"
      />

      <ChatInput @send="sendMessage" @upload="handleUpload" />
    </div>
  </div>
</template>

<style scoped>
.chat-layout {
  display: flex;
  height: calc(100vh - 56px);
}
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.chat-header {
  padding: 12px 24px;
  border-bottom: 1px solid #e8eaed;
  background: #fafbfc;
}
.chat-title {
  font-weight: 600;
  font-size: 15px;
}
.chat-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}
.welcome {
  text-align: center;
  max-width: 560px;
}
.welcome h2 {
  font-size: 32px;
  color: #409eff;
  margin-bottom: 8px;
}
.welcome-sub {
  color: #909399;
  margin-bottom: 32px;
  font-size: 15px;
}
.suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: center;
  margin-bottom: 28px;
}
.suggest-item {
  padding: 10px 18px;
  background: #fff;
  border: 1px solid #dcdfe6;
  border-radius: 20px;
  cursor: pointer;
  font-size: 14px;
  color: #606266;
  transition: border-color .2s, color .2s;
}
.suggest-item:hover {
  border-color: #409eff;
  color: #409eff;
}
.msg-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  margin: 0 auto;
}
.msg-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
}
</style>
