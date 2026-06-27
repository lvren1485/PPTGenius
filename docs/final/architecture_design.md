# PPTGenius Architecture Design

> 版本: 0.3.0 | 日期: 2026-06-17 | 基于 `docs/design/improvement.md` + `docs/implement/problem.md` + 实际代码

---

## 目录

1. [系统架构总览](#1-系统架构总览)
2. [目录结构](#2-目录结构)
3. [Unified Master Agent](#3-unified-master-agent)
4. [子 Agent 体系](#4-子-agent-体系)
5. [Slide Agent Part-Based 模型](#5-slide-agent-part-based-模型)
6. [质量检查与容错](#6-质量检查与容错)
7. [Middleware 三层架构](#7-middleware-三层架构)
8. [RAG / Web Search 基础设施](#8-rag--web-search-基础设施)
9. [PPT Engine 渲染管线](#9-ppt-engine-渲染管线)
10. [SSE 流式通信](#10-sse-流式通信)
11. [前端架构](#11-前端架构)
12. [配置体系](#12-配置体系)

---

## 1. 系统架构总览

```
                    用户消息 (唯一入口)
                           │
                           ▼
                ┌─────────────────────┐
                │   Unified Master    │  FastAPI POST /api/chat/send → SSE
                │   (单一 ReAct Agent) │  middleware: Persist + SSE + Token
                └──────┬──────────────┘
                       │
       ┌───────────────┼───────────────┬──────────────────┐
       ▼               ▼               ▼                  ▼
  perception      structure       outline_section    ppt_style
  (读DB, 9工具)   (写DB, 4工具)   (子Agent, 并行)    (子Agent)
                                       │                  │
                       ┌───────────────┤                  │
                       ▼               ▼                  ▼
                  explore_knowledge  generator       slides_content
                  (搜索+划分建议)    (写slides)       (N×Slide并行)
                                                         │
                                                         ▼
                                                   Assembly (infra)
                                                   读DB → 渲染.pptx
```

**核心设计：** 单一 Master Agent 作为唯一入口，所有 sub-agent 以 tool 形式平铺。Sub-agent 产出直接写 DB，tool result 仅返回一行确认。Master 自行读写 DB 感知进度。

---

## 2. 目录结构

```
backend/src/pptgenius/
├── agent/
│   ├── common/
│   │   ├── agent_registry.py       # Agent 生命周期 (push/pop sentinel)
│   │   ├── message_utils.py        # 消息序列化（retry 清理）
│   │   ├── sse_context.py          # SSE writer context var
│   │   └── middleware/
│   │       ├── persist_tool.py     # PersistToolMiddleware (逐步持久化)
│   │       ├── sse_tool.py         # SSEToolMiddleware (tool 事件推送)
│   │       └── token_tool.py       # TokenCountingMiddleware (用量统计)
│   ├── master.py                   # Unified Master (唯一入口, ~300行)
│   ├── tools/
│   │   ├── perception.py           # 感知层 (9 只读工具)
│   │   ├── structure.py            # 结构层 (4 写工具)
│   │   ├── explore_knowledge.py    # 知识探索 (搜索+划分)
│   │   ├── outline_section.py      # 章节大纲生成
│   │   ├── ppt_style.py            # PPT 样式选择
│   │   ├── slides_content.py       # 全页并行生成 (asyncio.gather)
│   │   └── slide_agent.py          # 单页三工具模型
│   ├── outline/
│   │   ├── explore.py              # Explore Agent (ReAct 搜索)
│   │   ├── generator.py            # Generator (write_slide + pending_slides)
│   │   ├── prompts.py              # Generator/Explore prompt
│   │   └── knowledge_tools.py      # search_knowledge/web/fetch/read_file
│   └── ppt/
│       ├── common/
│       │   ├── tools.py            # search_icons, read_instruction
│       │   └── instruction_loader.py
│       ├── slide_agent.py          # Slide Agent (submit_element/notes/bg/plan/check)
│       ├── slide_prompts.py        # Slide system prompt
│       └── style_agent.py          # Style Agent (get/save/set style)
├── infrastructure/
│   ├── config/                     # Settings + models (Pydantic)
│   ├── db/                         # ORM models + repository + engine
│   ├── llm/                        # LLM factory + DeepSeek adapter
│   ├── rag/                        # BM25 + web_search + summary + parser
│   ├── ppt_engine/                 # Assembly + generator + parser
│   ├── workspace/                  # Per-conversation file mgmt
│   └── utils/                      # Logger + TokenCounter
├── api/                            # FastAPI routers (13 files)
├── resources/                      # prompts, styles, fonts, layouts
└── main.py                         # App entry
```

---

## 3. Unified Master Agent

### 工具清单 (19 个)

**感知层** (`tools/perception.py`): `get_conversation_status`, `switch_outline`, `get_outline`, `get_outline_slide`, `get_pending_slides`, `get_pending_presentation_slides`, `get_presentation`, `get_knowledge_files`, `search_styles`
— 全部只读 DB，返回摘要。`conversation_id`/`outline_id` 闭包注入。

**结构层** (`tools/structure.py`): `create_empty_outline`, `write_outline_structure`, `modify_outline_structure`, `rearrange_presentation_slides`
— 写 DB（含 title_slide + ending_slide 自动补全）。

**子 Agent 工具** (执行层): `explore_knowledge`, `outline_section` (×N 并行), `ppt_style`, `slides_content`, `modify_slides_content`

### 子 Agent 工具识别

`_SUB_AGENT_TOOLS` 集合（按 `content_type` 识别，master.py:46）:
```python
{"gen_content", "mod_section", "explore", "ppt_style", "slides_content", "mod_slides"}
```

### 数据关系

```
conversations.current_outline_id → outlines(id)
outlines : presentations = 1 : N (通过 outline_id FK)
outlines.version — 单调递增 int
presentations.version + outline_version — 追踪 PPT/大纲版本关联
```

---

## 4. 子 Agent 体系

### Explore Agent (`outline/explore.py`)
- 工具: `search_knowledge`(≤12), `search_web`(≤8), `fetch_web`(≤6)
- 产出: JSON `{sections: [{title, description, knowledge_file_ids, key_chunk_ids}]}`
- 写入: `outlines.explore_result_json`

### Generator (`outline/generator.py`)
- 工具: `write_slide`, `pending_slides` (无搜索工具)
- 输入: Explore 的 file_id + chunk_id → 直接读 DB 全文拼入 prompt
- 输出: 结构化 Markdown → 解析后写 DB

### Slide Agent (`ppt/slide_agent.py`)
- 工具: `submit_element`, `submit_notes`, `submit_background`, `submit_plan`, `check_parts`
- 模型: 内存缓存 → Agent 结束一次性写 DB `agent_outputs`
- 注入: style 完整值 + template 预设 + z_order 参照表

### Style Agent (`ppt/style_agent.py`)
- 工具: `search_styles`, `get_style`, `save_style`, `set_presentation_style`
- 自动注入 outline_summary + 可用 styles 列表

---

## 5. Slide Agent Part-Based 模型

Slide Agent 是 PPT 生成的核心，每页 slide 独立运行一个 ReAct Agent（纯内存，无 DB 访问）。

### 工具集 (7 个)

| 工具 | 作用 |
|------|------|
| `submit_plan` | 定义/更新 part 布局方案，声明 bounds、内容类型、装饰风格 |
| `check_parts` | 查看进度 / 查看 part 详细元素 / 标记 part 完成 |
| `submit_element` | 添加 / 覆盖 / 删除元素（含校验 + 空间检查 + 装饰检查） |
| `submit_background` | 设置页面背景 (solid / gradient / image / no_fill) |
| `search_icons` | 从 Tabler Icons 搜索 SVG 图标 |
| `read_instruction` | 读取元素类型使用说明 |
| `read_chart_instruction` | 读取图表类型使用说明 |

### 生成流程

```
submit_plan (定义 parts + bounds)
  → submit_background (设置背景)
  → [submit_element × N] (逐个添加元素，每个归属某个 part)
  → check_parts(part="xxx", complete=true) (逐 part 标记完成)
  → Agent 退出 → 一次性写 DB
```

### 内存缓冲区

```python
_buffer = {
    "plan": {"design_concept": "...", "parts": {"标题区": {"status": "pending", ...}, ...}},
    "elements": {"a1b2c3d4": {type, position, fill, _part, ...}, ...},
    "background": {"type": "solid", "color": "F8FAFC"},
}
```

- `_elements` 中每个元素以 8-char hex id 为 key，`_part` 字段关联到 plan 中的 part
- Agent 结束时，`_buffer` 序列化为 `{slide_index, elements: [...], notes, background, plan}` 写入 `presentation_slides.agent_outputs`

### 修改模式

当 `existing_outputs` 非空时进入修改模式：

1. 已有元素预加载到 `_buffer`，保留 `_eid`
2. 保存 `_init_elements` / `_init_bg` 快照（崩溃恢复用）
3. 已有 plan 的所有 part 状态为 `complete`
4. LLM 需先 `check_parts()` 查看现状 → `submit_plan` 重提需修改的 part（重置为 pending）→ 逐 part 修改 → 标记完成

关键约束：**不需要改动的 part 不要重新提交 submit_plan**，否则会被重置为 pending。

### 重试机制

最多 3 次重试（`_MAX_RETRIES=3`）。每次重试后检查：
- 有 plan 且所有 part 都 complete 且有 elements/background → 成功退出
- 否则构造 state-aware 重试 prompt：
  - 有部分进度：告知 LLM 当前已有 N 个 part、M 个元素，列出未完成 part，要求继续
  - 崩溃重置：恢复 `_init_elements` / `_init_bg` 快照，从头开始

---

## 6. 质量检查与容错

### 6.1 空间检查 (`ppt/spatial_check.py`)

每个 `submit_element` 调用时自动执行：

| 检查项 | 逻辑 | 级别 |
|--------|------|------|
| 越界检查 | 元素超出 slide 边界 (13.33×7.5") | ⚠ 警告 |
| 重叠检测 | 与已有元素计算 IoU，>30% 触发 | ⚠ 警告 (非 shape) / ℹ 提示 (shape-shape) |
| 文字溢出 | 估算 textbox 容量 vs 实际文字量 | ⚠ 警告 |
| 最小尺寸 | chart ≥ 2×2", table ≥ 3×1.5", image ≥ 0.5×0.5" | ⚠ 警告 |

重叠检测带 z_order 感知：元素标签包含 `eid[:8] (type:subtype, z=N)` 方便 LLM 定位。
Shape-shape 重叠降级为 ℹ 级（装饰叠加是常见设计模式）。

### 6.2 Plan bounds 预检 (`check_plan_bounds`)

`submit_plan` 时检查各 part 的 bounds：
- 越界：超出 slide 范围
- 重叠：part 之间 bounds 重叠
- 最小尺寸：chart/table/image part 不满足最小要求

### 6.3 装饰风格统一 (`ppt/decor_check.py`)

同一 slide 内 emoji 与 SVG icon 二选一：
- Plan 中通过 `decor_style: "emoji" | "icon"` 声明
- `submit_element` 时检测冲突 → 硬拒绝
- 未声明时首次提交自动推断

### 6.4 元素校验 (`ppt_engine/validator.py`)

`submit_element` 前经过 JSON Schema 校验：
- 必需字段：type, position (left, top, width, height)
- 类型特有字段：textbox 需 text_content, chart 需 chart_type + chart_data, 等
- 错误最多返回 10 条，LLM 可据此修正重提

### 6.5 字号体系

四级字号梯队，写入 style 的 `fonts_json`：

| 级别 | 字号 | 用途 |
|------|------|------|
| `body_title` | 16pt | 一级正文标题 |
| `body` | 14pt | 正文 |
| `body_small` | 12pt | 辅助说明 |
| `caption` | 11pt | 标注、脚注（最小字号） |

### 6.6 文本密度 (`text_density`)

与 `style_density`（控制装饰量）正交：

| 级别 | textbox 数量 | 单 box 字符 | 溢出阈值 |
|------|------------|-------------|---------|
| `sparse` | 1-2 | ~80 字 | capacity × 1.2 |
| `moderate` | 3-5 | ~200 字 | capacity × 1.5 |
| `dense` | 6-8 | ~400 字 | capacity × 2.0 |

---

## 7. Middleware 三层架构

注册于 `create_agent(middleware=[...])`，按注册反序执行:

```
PersistToolMiddleware.wrap_tool_call   ← ③ 先: 写 tool_call → DB
  SSEToolMiddleware.wrap_tool_call     ← ② 次: 发 tool_start SSE
    TokenCountingMiddleware            ← ① 无 wrap_tool_call
      handler(request)                 ← 工具执行
  SSEToolMiddleware                    ← 发 tool_end/tool_error SSE
PersistToolMiddleware                  ← 写 tool_result → DB
```

**删除项**: `tool_sse_wrapper.py` (被 SSEToolMiddleware 替代)、`master.py::_persist_tool_messages` (被 PersistToolMiddleware 替代)。

---

## 8. RAG / Web Search 基础设施

### BM25 检索 (`infrastructure/rag/`)
- `KnowledgeService`: build_index / search / search_by_conversation / ingest / remove
- 双索引: 全局 (user 级) + 会话 (conversation 级)
- `SummaryService`: 文件上传/网页抓取后自动 LLM 摘要

### Web Search (`infrastructure/rag/web_search.py`)
- 引擎: DuckDuckGo (HTML 抓取) | SearXNG (JSON API)
- 配置切换: `web_search.engine: "searxng"` + `searxng_base_url`
- SearXNG Docker 部署, 端口 8080, settings.yml 关限流

---

## 9. PPT Engine 渲染管线

```
assemble_pptx(db, presentation_id, conv_id, user_id)
  1. 读 presentation_slides.agent_outputs
  2. 每页 elements 按 z_order 排序 → 顺序添加 (后加=上层)
  3. 读 outline_slides.citations → 查 knowledge_files → 增写 notes 引用
  4. 调 generator.generate_pptx() → 写 .pptx 文件
  5. 导出 snapshot
```

z_order 参照: `background(0) → bg_image(10) → shape(20) → picture(30) → chart(40) → table(50) → small_shape(60) → textbox(70) → title(80) → page_number(90)`

---

## 10. SSE 流式通信

**协议:** `POST /api/chat/send` → SSE stream (`text/event-stream`)

**事件类型** (`event: message`, data.type):
| type | 触发 | 前端行为 |
|------|------|---------|
| `master_start` | Master 开始 | thinking=true, 显示加载气泡 |
| `tool_start` | 工具调用开始 | 推入 ToolCallCard |
| `tool_end` | 工具调用结束 | 推入 tool_result |
| `tool_error` | 工具异常 | 推入错误信息 |
| `document` | 产出大纲/PPT | 推入 DocumentCard |
| `master_reply` | Master 文本回复 | 推入 MessageBubble (AI) |
| `master_done` | Master 结束 | thinking=false |
| `done` | 流结束 | loadConversation() |
| `error` | 错误 | ElMessage.error |

---

## 11. 前端架构

```
frontend/src/
├── api/
│   ├── client.ts       # Axios (baseURL=/api, auth interceptor)
│   └── sse.ts           # SSE streamChat generator
├── stores/auth.ts       # Pinia auth (remember-me 7d TTL)
├── router/index.ts      # 9 routes + auth guard
├── views/
│   ├── ChatView.vue     # SSE 处理 + visibleMessages (工具分组)
│   ├── OutlineDetail/ListView, PptDetail/ListView
│   ├── LoginView, RegisterView, CostView, KnowledgeView
├── components/
│   ├── chat/            # ToolCallCard (二级折叠), PptPreview, DocumentCard
│   │                     MessageBubble, ChatInput, FileCard
│   ├── common/          # ListItemCard, EmptyState
│   └── layout/          # AppHeader (主题切换), ConversationSidebar
└── styles/global.css    # CSS变量 (亮/暗主题)
```

**ToolCallCard 两级折叠**: Master 工具（`_` 前缀且不在排除集）→ 一级 step，子 Agent 工具 → 二级嵌套。`SUB_TOOL_UNDERSCORE` 排除集纠正命名例外。上限 30 条。

---

## 12. 配置体系

```
config.yaml          → 默认值（提交版本控制）
config.local.yaml    → 本地覆盖（含 API key，不提交）
Settings Pydantic    → models.py 类型校验
```

配置段: `workspace`, `rag`, `agent` (outline + cache), `llm`, `db`, `log`, `web_search`

关键字段:
- `agent.cache.summarize_threshold: 0.7` — context_usage 超此值触发对话摘要
- `web_search.engine: "searxng" | "duckduckgo"`
- `web_search.searxng_base_url: "http://localhost:8080"` (engine=searxng 必需)
