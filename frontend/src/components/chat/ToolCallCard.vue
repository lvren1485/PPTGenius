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

const props = defineProps<{ items: ToolMsg[] }>()

const expanded = ref(false)

const pairs = computed(() => {
  const result: { call: ToolMsg | null; result: ToolMsg | null }[] = []
  let current: { call: ToolMsg | null; result: ToolMsg | null } = { call: null, result: null }
  for (const m of props.items) {
    if (m.role === 'tool_call') {
      if (current.call) result.push({ ...current })
      current = { call: m, result: null }
    } else if (m.role === 'tool_result') {
      if (current.call) {
        current.result = m
        result.push({ ...current })
        current = { call: null, result: null }
      }
    }
  }
  if (current.call) result.push({ ...current })
  return result
})

const summary = computed(() => {
  const names = pairs.value.map(p => ctypeLabel(p.call?.content_type || ''))
  return names.join(' → ')
})

function ctypeLabel(ctype: string): string {
  const map: Record<string, string> = {
    conv_status: '读取会话状态',
    switch_outline: '切换大纲',
    get_outline: '读取大纲',
    get_slide: '读取大纲页面',
    get_pres: '读取PPT',
    get_kfiles: '读取知识文件',
    search_styles: '搜索样式',
    create_outline: '创建大纲',
    write_outline: '写入大纲结构',
    mod_outline: '修改大纲结构',
    rearr_pres: '重排PPT',
    gen_content: '生成大纲内容',
    mod_section: '修改大纲章节',
    evaluate: '评估大纲',
    explore: '探索知识库',
    ppt_style: '选择样式',
    slides_content: '生成幻灯片',
    mod_slides: '修改幻灯片',
    tool_call: '工具调用',
    tool_result: '返回结果',
  }
  return map[ctype] || ctype
}

function toolName(meta: Record<string, any> | null): string {
  if (!meta) return ''
  return meta.tool_name || ''
}

function toolNameLabel(name: string): string {
  const map: Record<string, string> = {
    _get_conversation_status: '读取会话状态',
    _switch_outline: '切换大纲',
    _get_outline: '读取大纲',
    _get_outline_slide: '读取页面',
    _get_presentation: '读取PPT',
    _get_knowledge_files: '读取知识文件',
    _search_styles: '搜索样式',
    _create_empty_outline: '创建空大纲',
    _write_outline_structure: '写入大纲结构',
    _modify_outline_structure: '修改大纲结构',
    _rearrange_presentation_slides: '重排PPT',
    _generate_outline_content: '生成大纲内容',
    _modify_outline_section: '修改章节',
    _outline_evaluate: '评估大纲',
    _explore_knowledge: '探索知识库',
    _ppt_style: '选择样式',
    _slides_content: '生成幻灯片',
    _modify_slides_content: '修改幻灯片',
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
      <el-icon :class="{ rotated: expanded }"><CaretBottom /></el-icon>
      <span class="tool-summary">工具调用：{{ summary }}</span>
      <span class="tool-count">{{ pairs.length }} 步</span>
    </div>
    <div v-show="expanded" class="tool-body">
      <div v-for="(p, i) in pairs" :key="i" class="tool-step">
        <div class="tool-step-header">
          <span class="step-num">{{ i + 1 }}</span>
          <el-tag size="small" type="primary">{{ toolNameLabel(p.call?.metadata_json?.tool_name || '') || ctypeLabel(p.call?.content_type || '') }}</el-tag>
          <span class="step-ctype">{{ p.call?.content_type }}</span>
        </div>
        <div v-if="p.result" class="tool-result">
          {{ truncate(p.result.content) }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tool-card {
  margin-bottom: 12px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  background: #f5f7fa;
  max-width: 80%;
  align-self: flex-start;
  font-size: 13px;
}
.tool-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  user-select: none;
}
.tool-header:hover {
  background: #ebeef5;
  border-radius: 8px;
}
.tool-header .el-icon {
  transition: transform .2s;
  font-size: 12px;
  color: #909399;
}
.tool-header .el-icon.rotated {
  transform: rotate(-90deg);
}
.tool-summary {
  flex: 1;
  color: #606266;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tool-count {
  color: #c0c4cc;
  font-size: 12px;
  flex-shrink: 0;
}
.tool-body {
  border-top: 1px solid #e4e7ed;
  padding: 8px 12px;
}
.tool-step {
  padding: 6px 0;
}
.tool-step + .tool-step {
  border-top: 1px dashed #e4e7ed;
}
.tool-step-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}
.step-num {
  font-weight: 600;
  color: #409eff;
  min-width: 18px;
}
.step-ctype {
  font-size: 12px;
  color: #c0c4cc;
}
.tool-result {
  font-size: 12px;
  color: #909399;
  padding: 4px 8px;
  background: #fff;
  border-radius: 4px;
  line-height: 1.5;
  max-height: 60px;
  overflow: hidden;
}
</style>
