<script setup lang="ts">
import { ref, computed } from 'vue'
import { CaretBottom } from '@element-plus/icons-vue'

interface ToolMsg {
  id: number
  idx: number
  role: string
  content: string
  content_type: string | null
  metadata_json: Record<string, any> | null
}

interface ToolGroup {
  call: ToolMsg
  result: ToolMsg | null
  children: ToolMsg[]
}

const props = defineProps<{ items: ToolMsg[]; thinking?: boolean }>()

const expanded = ref(false)

// Sub-agent tools that happen to start with _ — must NOT be treated as master
const SUB_TOOL_UNDERSCORE = new Set([
  '_get_style', '_save_style', '_set_presentation_style',
  '_submit_element', '_submit_notes', '_submit_background',
  '_submit_plan', '_check_parts',
])

// Group: master tools (name starts with _) contain sub-agent tools as children
const groups = computed(() => {
  const result: ToolGroup[] = []
  let current: ToolGroup | null = null

  for (const m of props.items) {
    const name = m.metadata_json?.tool_name || ''
    const isMaster = name.startsWith('_') && !SUB_TOOL_UNDERSCORE.has(name)

    if (isMaster && m.role === 'tool_call') {
      if (current) result.push(current)
      current = { call: m, result: null, children: [] }
    } else if (isMaster && m.role === 'tool_result') {
      if (current && current.call.metadata_json?.tool_name === name) {
        current.result = m
        result.push(current)
        current = null
      }
    } else if (current) {
      // Sub-agent tool — goes inside current parent
      current.children.push(m)
    } else if (m.role === 'tool_call') {
      // Orphan tool (no parent context, name doesn't start with _)
      current = { call: m, result: null, children: [] }
    }
  }
  if (current) result.push(current)
  return result
})

const SUB_TOOL_LIMIT = 30

// Flatten sub-agent children into call/result pairs
function childPairs(children: ToolMsg[]) {
  const pending: { call: ToolMsg | null; result: ToolMsg | null }[] = []
  for (const m of children) {
    if (m.role === 'tool_call') {
      pending.push({ call: m, result: null })
    } else if (m.role === 'tool_result') {
      const name = m.metadata_json?.tool_name || ''
      const idx = pending.findIndex(p => !p.result && p.call?.metadata_json?.tool_name === name)
      if (idx >= 0) { pending[idx].result = m }
      else { pending.push({ call: null, result: m }) }
    }
  }
  return pending
}
function limitedPairs(children: ToolMsg[]) { return childPairs(children).slice(0, SUB_TOOL_LIMIT) }
function totalPairs(children: ToolMsg[]) { return childPairs(children).length }

const summary = computed(() => {
  const names = groups.value.map(g => ctypeLabel(g.call.content_type || ''))
  return names.join(' → ')
})

// Per-group sub-expand state
const subExpand = ref<Record<number, boolean>>({})

function toggleSub(i: number) {
  subExpand.value[i] = !subExpand.value[i]
}

function ctypeLabel(ctype: string): string {
  const map: Record<string, string> = {
    conv_status: '读取会话状态', switch_outline: '切换大纲',
    get_outline: '读取大纲', get_slide: '读取大纲页面',
    get_pres: '读取PPT', get_kfiles: '读取知识文件',
    search_styles: '搜索样式', create_outline: '创建大纲',
    write_outline: '写入大纲结构', mod_outline: '修改大纲结构',
    rearr_pres: '重排PPT', gen_content: '生成大纲内容',
    mod_section: '修改大纲章节', evaluate: '评估大纲',
    explore: '探索知识库', ppt_style: '选择样式',
    slides_content: '生成幻灯片', mod_slides: '修改幻灯片',
    get_style: '查看样式', save_style: '保存样式',
    set_pres_style: '应用样式', submit_elem: '提交元素',
    submit_notes: '提交备注', submit_bg: '提交背景',
    submit_plan: '提交计划', check_parts: '检查部件',
    pending_slides: '查看进度', pending_ppt_slides: '查看PPT进度',
  }
  return map[ctype] || ctype
}

function toolNameLabel(name: string): string {
  const map: Record<string, string> = {
    _get_conversation_status: '读取会话状态', _switch_outline: '切换大纲',
    _get_outline: '读取大纲', _get_outline_slide: '读取页面',
    _get_pending_slides: '查看大纲进度', _get_pending_presentation_slides: '查看PPT进度',
    _get_presentation: '读取PPT', _get_knowledge_files: '读取知识文件',
    _search_styles: '搜索样式', _create_empty_outline: '创建空大纲',
    _write_outline_structure: '写入大纲结构', _modify_outline_structure: '修改大纲结构',
    _rearrange_presentation_slides: '重排PPT', _generate_outline_content: '生成大纲内容',
    _modify_outline_section: '修改章节', _outline_evaluate: '评估大纲',
    _explore_knowledge: '探索知识库', _ppt_style: '选择样式',
    _slides_content: '生成幻灯片', _modify_slides_content: '修改幻灯片',
    search_knowledge: '搜索知识库', search_web: '网络搜索',
    fetch_web: '抓取网页', read_file: '读取文件',
    write_slide: '写入页面', pending_slides: '查看进度',
    search_icons: '搜索图标', read_instruction: '读取说明',
    read_chart_instruction: '读取图表说明',
    _submit_element: '提交元素', _submit_notes: '提交备注',
    _submit_background: '提交背景', _submit_plan: '提交计划',
    _check_parts: '检查部件',
    _get_style: '查看样式', _save_style: '保存样式',
    _set_presentation_style: '应用样式',
  }
  return map[name] || name
}

function truncate(s: string, max: number = 80): string {
  if (s.length <= max) return s
  return s.slice(0, max) + '...'
}
</script>

<template>
  <div class="tool-card">
    <div class="tool-header" @click="expanded = !expanded">
      <el-icon :class="{ rotated: !expanded }"><CaretBottom /></el-icon>
      <span class="tool-summary">{{ summary }}</span>
      <span class="tool-count">{{ groups.length }} 步</span>
    </div>
    <div v-show="expanded" class="tool-body">
      <template v-for="(g, gi) in groups" :key="gi">
        <div class="tool-group">
          <!-- Master tool -->
          <div class="master-step">
            <div class="tool-step-header">
              <span class="step-num">{{ gi + 1 }}</span>
              <el-tag size="small" type="primary">
                {{ toolNameLabel(g.call.metadata_json?.tool_name || '') || ctypeLabel(g.call.content_type || '') }}
              </el-tag>
              <span class="step-ctype">{{ g.call.content_type }}</span>
              <span v-if="!g.result && thinking && gi === groups.length - 1 && g.children.length === 0"
                class="thinking-dots"><i>.</i><i>.</i><i>.</i></span>
            </div>
            <div v-if="g.result" class="tool-result">{{ truncate(g.result.content) }}</div>
            <div v-else-if="thinking && gi === groups.length - 1 && g.children.length === 0"
              class="tool-result thinking-line" />
          </div>

          <!-- Sub-agent tools collapse -->
          <div v-if="g.children.length > 0" class="sub-wrap">
            <div class="sub-header" @click="toggleSub(gi)">
              <el-icon :class="{ rotated: !subExpand[gi] }"><CaretBottom /></el-icon>
              <span class="sub-summary">子工具 · {{ totalPairs(g.children) }} 步{{ totalPairs(g.children) > SUB_TOOL_LIMIT ? `（仅展示前${SUB_TOOL_LIMIT}条）` : '' }}</span>
              <span v-if="!g.result && thinking && gi === groups.length - 1"
                class="thinking-dots"><i>.</i><i>.</i><i>.</i></span>
            </div>
            <div v-show="subExpand[gi]" class="sub-body">
              <div v-for="(p, i) in limitedPairs(g.children)" :key="i" class="sub-step">
                <div class="tool-step-header">
                  <span class="step-num sub-num">{{ i + 1 }}</span>
                  <el-tag v-if="p.call" size="small">{{ toolNameLabel(p.call.metadata_json?.tool_name || '') }}</el-tag>
                  <el-tag v-else size="small" type="info">结果</el-tag>
                  <span v-if="!p.result && thinking && gi === groups.length - 1 && i === limitedPairs(g.children).length - 1"
                    class="thinking-dots"><i>.</i><i>.</i><i>.</i></span>
                </div>
                <div v-if="p.result" class="tool-result sub-result">{{ truncate(p.result.content, 60) }}</div>
                <div v-else-if="thinking && gi === groups.length - 1 && i === limitedPairs(g.children).length - 1"
                  class="tool-result thinking-line" />
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.tool-card {
  margin-bottom: 12px; border: 1px solid #e4e7ed; border-radius: 8px;
  background: var(--bg-card); max-width: 80%; align-self: flex-start; font-size: 13px; box-shadow: var(--shadow);
}
.tool-header {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px; cursor: pointer; user-select: none;
}
.tool-header:hover { background: var(--bg-hover); border-radius: 8px; }
.tool-header .el-icon { transition: transform .2s; font-size: 12px; color: var(--text-muted); }
.tool-header .el-icon.rotated { transform: rotate(-90deg); }
.tool-summary { flex: 1; color: var(--text-secondary); font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tool-count { color: var(--text-muted); font-size: 12px; flex-shrink: 0; }
.tool-body { border-top: 1px solid var(--border); padding: 8px 12px; }
.tool-group + .tool-group { border-top: 1px dashed var(--border); padding-top: 8px; margin-top: 4px; }
.master-step { padding: 4px 0; }
.tool-step-header { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.step-num { font-weight: 600; color: var(--primary); min-width: 18px; }
.sub-num { color: var(--text-muted); font-size: 12px; min-width: 16px; }
.step-ctype { font-size: 12px; color: var(--text-muted); }
.tool-result { font-size: 12px; color: var(--text-secondary); padding: 4px 8px; background: var(--bg-hover); border-radius: 4px; line-height: 1.5; max-height: 60px; overflow: hidden; }
.thinking-line { height: 20px; background: linear-gradient(90deg, var(--primary-bg), var(--primary-border), var(--primary-bg)); background-size: 200% 100%; animation: shimmer 1.5s infinite; padding: 0; }
.thinking-dots i { font-style: normal; font-weight: 700; color: var(--primary); animation: dotBounce 1.4s infinite; }
.thinking-dots i:nth-child(2) { animation-delay: .2s; }
.thinking-dots i:nth-child(3) { animation-delay: .4s; }

.sub-wrap { margin: 4px 0 0 18px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); }
.sub-header { display: flex; align-items: center; gap: 6px; padding: 4px 10px; cursor: pointer; user-select: none; }
.sub-header:hover { background: var(--bg-hover); border-radius: 6px; }
.sub-header .el-icon { transition: transform .2s; font-size: 11px; color: var(--text-muted); }
.sub-header .el-icon.rotated { transform: rotate(-90deg); }
.sub-summary { font-size: 12px; color: var(--text-muted); flex: 1; }
.sub-body { border-top: 1px solid var(--border-light); padding: 4px 10px; }
.sub-step { padding: 3px 0; }
.sub-step + .sub-step { border-top: 1px dotted var(--border-light); }
.sub-result { font-size: 11px; }

@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
@keyframes dotBounce { 0%, 80%, 100% { opacity: .2; } 40% { opacity: 1; } }
</style>
