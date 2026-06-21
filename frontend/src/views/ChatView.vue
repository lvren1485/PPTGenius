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
import ToolCallCard from '../components/chat/ToolCallCard.vue'
import ChatInput from '../components/chat/ChatInput.vue'

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

interface ToolBlock {
  _tool: true
  items: MsgItem[]
  idx: number
}

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const convId = computed(() => {
  const id = Number(route.params.id)
  return isNaN(id) ? 0 : id
})

const messages = ref<MsgItem[]>([])
const thinking = ref(false)
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

    thinking.value = true
    scrollBottom()

    try {
      for await (const evt of streamChat(cid, text)) {
        handleSseEvent(evt)
      }
    } catch (e: any) {
      ElMessage.error(e.message || '请求失败')
    } finally {
      thinking.value = false
    }

    await loadConversation()
    scrollBottom()
  } finally {
    sending.value = false
  }
}

function handleStop() {
  if (convId.value > 0) cancelChat(convId.value).catch(() => {})
  thinking.value = false
}

function handleSseEvent(evt: { event: string; data: Record<string, any> }) {
  const d = evt.data
  if (evt.event === 'error') { ElMessage.error(d.message || '执行出错'); return }
  if (evt.event === 'done') { thinking.value = false; return }
  if (evt.event !== 'message') return

  switch (d.type) {
    case 'master_start':
      thinking.value = true
      break
    case 'tool_start':
      messages.value.push({
        id: 0, idx: messages.value.length + 1,
        role: 'tool_call', content: d.tool || '',
        content_type: toolCtype(d.tool || ''),
        metadata_json: { tool_name: d.tool, args: d.args || {} },
        estimated_cost: null, created_at: new Date().toISOString(),
      })
      scrollBottom()
      break
    case 'tool_end':
      messages.value.push({
        id: 0, idx: messages.value.length + 1,
        role: 'tool_result', content: `完成 (${d.result_len || 0} 字符)`,
        content_type: toolCtype(d.tool || ''),
        metadata_json: { tool_name: d.tool, result_len: d.result_len },
        estimated_cost: null, created_at: new Date().toISOString(),
      })
      scrollBottom()
      break
    case 'tool_error':
      messages.value.push({
        id: 0, idx: messages.value.length + 1,
        role: 'tool_result', content: `错误: ${d.error || '未知错误'}`,
        content_type: toolCtype(d.tool || ''),
        metadata_json: { tool_name: d.tool, error: d.error },
        estimated_cost: null, created_at: new Date().toISOString(),
      })
      scrollBottom()
      break
    case 'document':
      messages.value.push({
        id: 0, idx: messages.value.length + 1,
        role: 'document', content: d.title || '',
        content_type: d.doc_type,
        metadata_json: d.doc_type === 'outline'
          ? { outline_id: d.snapshot_id, title: d.title }
          : { presentation_id: d.snapshot_id, title: d.title },
        estimated_cost: null, created_at: new Date().toISOString(),
      })
      scrollBottom()
      break
    case 'master_reply':
      messages.value.push({
        id: 0, idx: messages.value.length + 1,
        role: 'assistant', content: d.reply || '',
        content_type: 'text', metadata_json: null,
        estimated_cost: null, created_at: new Date().toISOString(),
      })
      scrollBottom()
      break
    case 'master_done':
      thinking.value = false
      break
  }
}

function toolCtype(name: string): string {
  const map: Record<string, string> = {
    _get_conversation_status: 'conv_status',
    _switch_outline: 'switch_outline',
    _get_outline: 'get_outline',
    _get_outline_slide: 'get_slide',
    _get_presentation: 'get_pres',
    _get_knowledge_files: 'get_kfiles',
    _search_styles: 'search_styles',
    _create_empty_outline: 'create_outline',
    _write_outline_structure: 'write_outline',
    _modify_outline_structure: 'mod_outline',
    _rearrange_presentation_slides: 'rearr_pres',
    _generate_outline_content: 'gen_content',
    _modify_outline_section: 'mod_section',
    _outline_evaluate: 'evaluate',
    _explore_knowledge: 'explore',
    _ppt_style: 'ppt_style',
    _slides_content: 'slides_content',
    _modify_slides_content: 'mod_slides',
  }
  return map[name] || 'tool_call'
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
  const result: (MsgItem | ToolBlock)[] = []
  const docs: MsgItem[] = []
  let toolBuf: MsgItem[] = []

  for (const m of messages.value) {
    if (m.role === 'tool_call' || m.role === 'tool_result') {
      toolBuf.push(m)
      continue
    }
    // Flush tool buffer before non-tool message
    if (toolBuf.length > 0) {
      result.push({ _tool: true, items: [...toolBuf], idx: toolBuf[0].idx })
      toolBuf = []
    }
    if (m.role === 'document') {
      docs.push(m)
    } else {
      result.push(m)
    }
  }
  // Flush remaining tools
  if (toolBuf.length > 0) {
    result.push({ _tool: true, items: [...toolBuf], idx: toolBuf[0].idx })
  }

  const keptDocs = docs.slice(-5)
  const all = [...result, ...keptDocs]
  all.sort((a, b) => a.idx - b.idx)
  return all
})

function renderMsg(msg: MsgItem) {
  if (msg.role === 'document') return 'document'
  if (msg.content_type === 'file') return 'file'
  return 'text'
}

function isToolBlock(item: MsgItem | ToolBlock): item is ToolBlock {
  return '_tool' in item
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
        <template v-for="msg in visibleMessages" :key="'id' in msg ? msg.id : msg.idx">
          <ToolCallCard
            v-if="isToolBlock(msg)"
            :items="(msg as any).items"
            :thinking="thinking"
          />
          <MessageBubble
            v-else-if="renderMsg(msg as MsgItem) === 'text'"
            :role="(msg as MsgItem).role"
            :content="(msg as MsgItem).content"
            :content_type="(msg as MsgItem).content_type"
            :created-at="(msg as MsgItem).created_at"
          />
          <FileCard
            v-else-if="renderMsg(msg as MsgItem) === 'file'"
            :content="(msg as MsgItem).content"
            :created-at="(msg as MsgItem).created_at"
          />
          <DocumentCard
            v-else-if="renderMsg(msg as MsgItem) === 'document'"
            :doc-type="(msg as MsgItem).content_type || ''"
            :metadata="(msg as MsgItem).metadata_json || {}"
            :content="(msg as MsgItem).content"
          />
        </template>
      </div>

      <ChatInput :sending="sending" @send="sendMessage" @stop="handleStop" @upload="handleUpload" />
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
