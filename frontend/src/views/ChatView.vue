<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api/client'
import { useAuthStore } from '../stores/auth'
import { streamChat, cancelChat } from '../api/sse'
import ConversationSidebar from '../components/layout/ConversationSidebar.vue'
import MessageBubble from '../components/chat/MessageBubble.vue'
import FileCard from '../components/chat/FileCard.vue'
import DocumentCard from '../components/chat/DocumentCard.vue'
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
  detail: string
  slideIndex: number
}

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const convId = computed(() => {
  const id = Number(route.params.id)
  return isNaN(id) ? 0 : id
})

const messages = ref<MsgItem[]>([])
const sse = ref<SseState>({ phase: '', detail: '', slideIndex: 0 })
const convTitle = ref('')

const suggestions = [
  '做一个关于Python数据分析的PPT',
  '介绍人工智能的发展历程',
  '制作一份产品发布会的演示文稿',
  '整理一份毕业论文答辩PPT',
  '制作公司年度总结报告',
]

watch(convId, async (id) => {
  if (sending.value) return
  if (id > 0) {
    await loadConversation()
    scrollBottom()
    const msg = route.query.msg as string
    if (msg) {
      router.replace({ query: {} })
      await sendMessage(msg)
    }
  } else {
    messages.value = []
    convTitle.value = ''
  }
})

onMounted(async () => {
  if (convId.value > 0) {
    await loadConversation()
    scrollBottom()
    const msg = route.query.msg as string
    if (msg) {
      router.replace({ query: {} })
      await sendMessage(msg)
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

const sending = ref(false)

async function ensureConversation(title?: string): Promise<number> {
  if (convId.value > 0) return convId.value
  const { data } = await api.post('/conversations', {
    user_id: auth.userId,
    title: title || '新对话',
  })
  const id = data.data.id
  await router.replace(`/chat/${id}`)
  await nextTick()
  return id
}

async function sendMessage(text: string) {
  if (!text.trim() || sending.value) return
  sending.value = true
  try {
    const cid = await ensureConversation(text.slice(0, 10))

    messages.value.push({
      id: 0, idx: messages.value.length + 1,
      role: 'user', content: text, content_type: 'text',
      metadata_json: null, estimated_cost: null, created_at: new Date().toISOString(),
    })
    await nextTick()
    scrollBottom()

    sse.value = { phase: '正在分析需求...', detail: '', slideIndex: 0 }
    const loadingIdx = messages.value.length + 1
    messages.value.push({
      id: -1, idx: loadingIdx,
      role: 'assistant', content: '...', content_type: 'text',
      metadata_json: null, estimated_cost: null, created_at: new Date().toISOString(),
    })
    scrollBottom()

    try {
      for await (const evt of streamChat(cid, text)) {
        if (messages.value.some(m => m.id === -1)) {
          messages.value = messages.value.filter(m => m.id !== -1)
        }
        handleSseEvent(evt)
      }
    } catch (e: any) {
      ElMessage.error(e.message || '请求失败')
      messages.value = messages.value.filter(m => m.id !== -1)
    } finally {
      sse.value = { phase: '', detail: '', slideIndex: 0 }
    }

    await loadConversation()
    scrollBottom()
  } finally {
    sending.value = false
  }
}

function handleStop() {
  if (convId.value > 0) {
    cancelChat(convId.value).catch(() => {})
  }
  ElMessage.info('正在停止...')
}

function handleSseEvent(evt: { event: string; data: Record<string, any> }) {
  const d = evt.data
  if (evt.event === 'error') {
    ElMessage.error(d.message || '执行出错')
    return
  }
  if (evt.event === 'done') {
    sse.value = { phase: '', detail: '', slideIndex: 0 }
    return
  }
  // evt.event === 'message' — 按内部 type 分发
  switch (d.type) {
    case 'master_start':
      sse.value = { ...sse.value, phase: '正在分析需求...', detail: '' }
      break
    case 'explore_agent_start':
      sse.value = { ...sse.value, phase: '正在搜索知识库...', detail: '' }
      break
    case 'outline_generator_start':
      sse.value = { ...sse.value, phase: '正在生成大纲...', detail: d.section || '' }
      break
    case 'outline_generator_end':
      sse.value = { ...sse.value, detail: '' }
      break
    case 'outline_evaluator_start':
      sse.value = { ...sse.value, phase: '正在评估大纲...', detail: d.outline || '' }
      break
    case 'style_agent_start':
      sse.value = { ...sse.value, phase: '正在选择样式...', detail: '' }
      break
    case 'slide_agent_start':
      sse.value = { ...sse.value, phase: '正在生成幻灯片...', slideIndex: d.slide_index || 1, detail: '' }
      break
    case 'tool_start':
      sse.value = { ...sse.value, detail: toolLabel(d.tool || '') }
      break
    case 'tool_end':
    case 'tool_error':
      sse.value = { ...sse.value, detail: '' }
      break
    case 'document':
      messages.value.push({
        id: 0, idx: messages.value.length + 1,
        role: 'document',
        content: d.title || '',
        content_type: d.doc_type,
        metadata_json: d.doc_type === 'outline'
          ? { outline_id: d.snapshot_id, title: d.title }
          : { presentation_id: d.snapshot_id, title: d.title },
        estimated_cost: null,
        created_at: new Date().toISOString(),
      })
      scrollBottom()
      break
    case 'master_reply':
      messages.value.push({
        id: 0, idx: messages.value.length + 1,
        role: 'assistant',
        content: d.reply || '',
        content_type: 'text',
        metadata_json: null,
        estimated_cost: null,
        created_at: new Date().toISOString(),
      })
      scrollBottom()
      break
    case 'master_done':
      sse.value = { phase: '', detail: '', slideIndex: 0 }
      break
  }
}

function toolLabel(name: string): string {
  const map: Record<string, string> = {
    _get_conversation_status: '读取会话状态',
    _switch_outline: '切换大纲',
    _get_outline: '读取大纲',
    _get_outline_slide: '读取大纲页面',
    _get_presentation: '读取PPT',
    _get_knowledge_files: '读取知识文件',
    _search_styles: '搜索样式',
    _create_empty_outline: '创建空白大纲',
    _write_outline_structure: '写入大纲结构',
    _modify_outline_structure: '修改大纲结构',
    _rearrange_presentation_slides: '重排PPT页面',
    _generate_outline_content: '生成大纲内容',
    _modify_outline_section: '修改大纲章节',
    _outline_evaluate: '评估大纲',
    _explore_knowledge: '探索知识库',
    _ppt_style: '选择样式',
    _slides_content: '生成幻灯片内容',
    _modify_slides_content: '修改幻灯片',
  }
  return map[name] || name
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

function scrollBottom() {
  nextTick(() => {
    const el = document.getElementById('msg-container')
    if (el) el.scrollTop = el.scrollHeight
  })
}

const visibleMessages = computed(() => {
  const docs: MsgItem[] = []
  const others: MsgItem[] = []
  for (const m of messages.value) {
    if (m.role === 'document') {
      docs.push(m)
    } else {
      others.push(m)
    }
  }
  const keptDocs = docs.slice(-5)
  const all = [...others, ...keptDocs]
  all.sort((a, b) => a.idx - b.idx)
  return all
})

function renderMsg(msg: MsgItem) {
  if (msg.role === 'document') return 'document'
  if (msg.content_type === 'file') return 'file'
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
        <template v-for="msg in visibleMessages" :key="msg.id || msg.idx">
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
          <DocumentCard
            v-else-if="renderMsg(msg) === 'document'"
            :doc-type="msg.content_type || ''"
            :metadata="msg.metadata_json || {}"
          />
        </template>
      </div>

      <SseStatus
        v-if="sse.phase"
        :phase="sse.phase"
        :detail="sse.detail"
        :slide-index="sse.slideIndex"
        :sending="sending"
        @stop="handleStop"
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
}
</style>
