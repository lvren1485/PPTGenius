# PPTGenius Agent 架构设计文档

> 版本: 0.4.0 | 日期: 2026-06-19 | 基于 `agent/` 目录实际代码 (31 files, 3,816 lines)

---

## 目录

- [1. 总体架构](#1-总体架构)
- [2. Master Agent](#2-master-agent)
- [3. Middleware 三层架构](#3-middleware-三层架构)
- [4. Sub-Agent 注册与 Token 追踪](#4-sub-agent-注册与-token-追踪)
- [5. 感知工具 (Perception)](#5-感知工具-perception)
- [6. 结构工具 (Structure)](#6-结构工具-structure)
- [7. Explore Agent](#7-explore-agent)
- [8. Outline Generator](#8-outline-generator)
- [9. Style Agent](#9-style-agent)
- [10. Slide Agent](#10-slide-agent)
- [11. 质量检查体系](#11-质量检查体系)
- [12. 数据流全景](#12-数据流全景)

---

## 1. 总体架构

### 1.1 设计原则

PPTGenius 采用**单一 Master + 扁平 Sub-Agent** 架构。所有用户请求由唯一的 Master Agent 处理，Master 通过 19 个 tool 感知状态、操作数据、调度 Sub-Agent。Sub-Agent 以 tool call 形式被调用，每个 Sub-Agent 拥有独立的 LLM 实例和 context window，执行完毕后将产出写入 DB，仅向 Master 返回一行确认摘要。

```
用户消息 (POST /api/chat/send → SSE)
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│                   Unified Master Agent                   │
│                                                         │
│  LLM: DeepSeek V4 Flash (ReAct, create_agent)           │
│  Middleware: Persist + SSE + TokenCounting               │
│  System Prompt: resources/prompts/master.md              │
│  Context: DB 加载历史消息 (最近 20 轮 / 摘要检查点后)     │
│                                                         │
│  ┌─────────────┐ ┌─────────────┐ ┌──────────────────┐   │
│  │ 感知工具 ×9 │ │ 结构工具 ×4 │ │ Sub-Agent 工具 ×6│   │
│  │ (只读 DB)   │ │ (写 DB)     │ │ (独立 LLM 调用) │   │
│  └─────────────┘ └─────────────┘ └──────────────────┘   │
└─────────────────────────────────────────────────────────┘
         │                                │
    DB 读写                          Sub-Agent 调用
         │                                │
         ▼                                ▼
┌──────────────┐    ┌─────────────────────────────────────┐
│   MySQL DB   │    │  Sub-Agents (各自独立 context)       │
│              │    │                                     │
│ conversations│    │  ┌──────────┐  ┌──────────────────┐ │
│ outlines     │    │  │ Explore  │  │ Generator × N    │ │
│ presentations│    │  │ (搜索)   │  │ (每 section 一个)│ │
│ messages     │    │  └──────────┘  └──────────────────┘ │
│ knowledge    │    │  ┌──────────┐  ┌──────────────────┐ │
│ styles       │    │  │ Style    │  │ Slide × N        │ │
│              │    │  │ (配色)   │  │ (每页一个)       │ │
└──────────────┘    │  └──────────┘  └──────────────────┘ │
                    └─────────────────────────────────────┘
```

### 1.2 关键设计约束

| 约束 | 原因 | 实现方式 |
|------|------|---------|
| **Context 隔离** | 避免 Sub-Agent 的 tool history 污染 Master 的 context | 每个 Sub-Agent 启动独立的 `create_llm()` 调用 |
| **产出写 DB** | 避免大 JSON 通过 tool_result 回传给 Master | Sub-Agent 直接写 DB，Master 通过感知工具读取 |
| **Tool result 简短** | 控制 Master context 增长 | 所有 tool 返回一行确认字符串 |
| **闭包注入** | 避免全局状态 | 每个 tool 通过 `make_xxx(db, conversation_id)` 闭包注入依赖 |
| **Sentinel 机制** | 区分多个并发 Sub-Agent 的 token 归属 | `push_sentinel()` → Sub-Agent 调用 → `pop_until_sentinel()` |

---

## 2. Master Agent

**文件**: `agent/master.py` (491 行)  
**入口**: `run_master_agent(db, conversation_id, user_message)`

### 2.1 执行流程

```
0. 检查 context_usage > 阈值 → 触发对话摘要压缩
1. create_llm() → 获取 LLM 实例 + agent_id
2. build_middlewares() → [Persist, SSE, TokenCounting]
3. _assemble_tools() → 19 个 tool
4. create_agent() → ReAct Agent (system_prompt 从 master.md 加载)
5. _load_context_messages() → 从 DB 恢复消息历史
6. agent.ainvoke() → 执行 (recursion_limit=80)
7. persist_mw.flush() → 持久化所有 tool_call/tool_result
8. 提取 reply + reasoning_content → 写入 messages 表
9. 检测 outline/presentation 变更 → 创建 snapshot + 发送 document SSE 事件
```

### 2.2 工具注册表

Master 的 19 个工具按职能分为三层：

| 层 | 工具 | 数量 | 文件 | 特征 |
|---|------|------|------|------|
| **感知层** | `get_conversation_status`, `switch_outline`, `get_outline`, `get_outline_slide`, `get_pending_slides`, `get_pending_presentation_slides`, `get_presentation`, `get_knowledge_files`, `search_styles` | 9 | `tools/perception.py` | 只读 DB，返回摘要 |
| **结构层** | `create_empty_outline`, `write_outline_structure`, `modify_outline_structure`, `rearrange_presentation_slides` | 4 | `tools/structure.py` | 写 DB，修改大纲/PPT 结构 |
| **执行层** | `explore_knowledge`, `generate_outline_content`, `modify_outline_section`, `ppt_style`, `slides_content`, `modify_slides_content` | 6 | `tools/explore_knowledge.py` 等 | 调用 Sub-Agent |

### 2.3 Content Type 映射

每个 tool 有一个 ≤32 字符的 `content_type`，用于 DB 持久化和前端渲染分组：

```python
_TOOL_CTYPE = {
    "_get_conversation_status":  "conv_status",
    "_slides_content":            "slides_content",
    "_modify_slides_content":     "mod_slides",
    ...  # 共 19 项
}
```

Sub-Agent 工具通过 `_SUB_AGENT_TOOLS` 集合标识，`PersistToolMiddleware` 据此在 tool_result 持久化时汇总子 Agent token 消耗：

```python
_SUB_AGENT_TOOLS = {"gen_content", "mod_section", "explore", "ppt_style", "slides_content", "mod_slides"}
```

### 2.4 Context 加载与摘要压缩

`_load_context_messages()` 从 DB 恢复 LangChain 消息链：

1. 查找最新的 `content_type="summary"` 消息作为摘要检查点
2. 检查点之前的历史压缩为一条 `HumanMessage("[对话历史摘要]\n\n{summary}")`
3. 检查点之后的消息逐条还原：
   - `user` / `file` / `image` → `HumanMessage`
   - `tool_call` + `tool_result` 配对 → `AIMessage(tool_calls=[...])` + `ToolMessage`
   - `assistant` → `AIMessage`
4. 不完整的 tool_call（无对应 tool_result）静默丢弃
5. `reasoning_content` 从 `metadata_json` 恢复到 `additional_kwargs`

摘要触发条件：`conversation.context_usage > summarize_threshold`（默认 0.7）

### 2.5 变更检测与快照

Master 执行完毕后检查新增消息中是否包含特定 tool name：

| 检测 | 触发工具 | 动作 |
|------|---------|------|
| `outline_changed` | `write_outline_structure`, `modify_outline_structure`, `generate_outline_content`, `modify_outline_section` | 版本号 +1，创建 outline_snapshot，发送 `document(outline)` SSE 事件 |
| `presentation_changed` | `slides_content`, `modify_slides_content`, `ppt_style`, `rearrange_presentation_slides` | 版本号 +1，创建 presentation_snapshot，发送 `document(presentation)` SSE 事件 |

---

## 3. Middleware 三层架构

**文件**: `agent/common/middleware/` (4 files, 297 行)  
**构建**: `build_middlewares(conversation_id, agent_id, ctypes?, sub_agent_types?)`

### 3.1 三层 Middleware

| 层 | 类 | 职责 | Master 使用 | Sub-Agent 使用 |
|---|---|------|-----------|--------------|
| ① | `PersistToolMiddleware` | 逐步持久化 tool_call/tool_result 到 messages 表 | ✓ | ✗ |
| ② | `SSEToolMiddleware` | 发送 tool_start/tool_end/tool_error SSE 事件 | ✓ | ✓ |
| ③ | `TokenCountingMiddleware` | 统计 input/output/reasoning tokens | ✓ | ✓ |

### 3.2 执行顺序

Middleware 按注册顺序的**反序**包裹 tool 调用：

```
Master 调用 tool:
  PersistToolMiddleware.pre  → 写 tool_call 消息到 DB
    SSEToolMiddleware.pre    → 发送 tool_start SSE
      TokenCountingMiddleware → 计数 tokens
        ════════════════════
        actual tool execution
        ════════════════════
      TokenCountingMiddleware → 更新计数
    SSEToolMiddleware.post   → 发送 tool_end SSE
  PersistToolMiddleware.post → 写 tool_result 消息到 DB
                              → 如果是 Sub-Agent 工具，pop_until_sentinel() 汇总子 Agent token
```

### 3.3 PersistToolMiddleware 详解

仅 Master 使用。每次 tool 调用时：

1. **pre**: 将 `AIMessage(tool_calls=[...])` 以 `role=tool_call` 写入 messages 表，`metadata_json` 包含 `{tool_name, args, tool_call_id, reasoning_content}`
2. **post**: 将 tool result 以 `role=tool_result` 写入 messages 表
3. **Sub-Agent 工具特殊处理**: post 阶段调用 `pop_until_sentinel()` 获取所有子 Agent 的 `agent_id`，汇总其 `TokenCounter` 数据，写入 tool_result 消息的 `token_cost_json`
4. **flush()**: Master 结束时调用，确保所有未写入的消息落盘

---

## 4. Sub-Agent 注册与 Token 追踪

**文件**: `agent/common/agent_registry.py` (42 行)

### 4.1 Sentinel 机制

Sub-Agent 工具的三段式调用协议：

```python
# ① Master 的 tool 包装层
push_sentinel(conversation_id)          # 标记子 Agent 批次开始

# ② Sub-Agent 内部
llm, agent_id = create_llm(conversation_id)
push_agent(conversation_id, agent_id)   # 注册自己的 agent_id

# ③ Master 的 PersistToolMiddleware.post
agent_ids = pop_until_sentinel(conversation_id)  # 获取本次调用的所有子 Agent ID
for aid in agent_ids:
    tc = TokenCounter.get_agent(aid)              # 汇总 token 消耗
```

### 4.2 并发安全

`_agents` 是一个 `dict[int, list[str]]` 栈结构，key 是 `conversation_id`。`push_sentinel` / `push_agent` / `pop_until_sentinel` 通过栈的 LIFO 语义保证正确性——即使多个 Sub-Agent 并发运行（如 `asyncio.gather`），它们的 `agent_id` 都会被 push 到同一个 sentinel 之上，`pop_until_sentinel` 一次性取出所有。

### 4.3 Token 统计双层结构

```
TokenCounter._conv_counters[conversation_id]    ← Master 的 token 统计
TokenCounter._agent_counters[agent_id]          ← 每个 Sub-Agent 的独立统计
```

- `agent_id` 不存入任何 DB 表，仅存在于内存中的 `TokenCounter`
- Sub-Agent 的 token 消耗在 `pop_until_sentinel()` 时汇总，写入对应 tool_result 消息的 `token_cost_json`
- Master 自身的 token 消耗在 `run_master_agent` 结尾写入 assistant 消息

---

## 5. 感知工具 (Perception)

**文件**: `agent/tools/perception.py` (362 行)  
**特征**: 全部只读 DB，返回摘要字符串

| 工具 | 功能 | 返回内容 |
|------|------|---------|
| `get_conversation_status` | 对话全局状态 | 大纲标题/版本/评分、PPT 状态/版本、知识文件列表 |
| `switch_outline` | 切换到指定大纲 | 确认消息 |
| `get_outline` | 当前大纲详情 | sections + slides 列表 |
| `get_outline_slide` | 单个 slide 详情 | content_json 完整内容 |
| `get_pending_slides` | 未完成的大纲 slides | status != completed 的列表 |
| `get_pending_presentation_slides` | 需重生成的 PPT slides | status 含 `o_modified_` 前缀的列表 |
| `get_presentation` | PPT 详情 | slide 列表 + agent_outputs 摘要 |
| `get_knowledge_files` | 知识文件列表 | file_id, filename, type, status |
| `search_styles` | 搜索可用样式 | name, label, colors 摘要 |

所有工具通过 `make_xxx(db, conversation_id)` 闭包注入 DB 和 conversation_id，内部无状态。

---

## 6. 结构工具 (Structure)

**文件**: `agent/tools/structure.py` (471 行)  
**特征**: 写 DB，修改大纲和 PPT 的结构性数据

| 工具 | 功能 | 关键逻辑 |
|------|------|---------|
| `create_empty_outline` | 创建空白大纲 | 设为 conversation 当前大纲 |
| `write_outline_structure` | 写入完整大纲结构 | 软删旧 slides/sections → 创建新 sections + slides (title/section/content/thanks) |
| `modify_outline_structure` | 修改大纲结构 | rename/delete/insert/move 四种 op，内存操作后批量 reindex |
| `rearrange_presentation_slides` | 同步 PPT slides 与大纲 | 删除 `o_modified_deleted`，创建缺失 slides，reindex |

### 6.1 modify_outline_structure 设计

操作在内存中的 `slide_list` 上执行，避免逐条 UPDATE 触发唯一约束冲突：

```
1. 从 DB 加载所有 live slides → sorted list
2. 逐个应用 operations (rename/delete/insert/move)
3. 每次操作后重建 _id_to_pos 索引
4. 全部完成后 reindex_outline_slides() 批量 UPDATE (两步法: 先设负数 → 再设目标值)
5. _cascade_pres_status() 标记对应 PPT slides 需要更新
```

### 6.2 Cascade 级联机制

outline 结构变更时，通过 `_cascade_pres_status()` 同步标记 presentation_slides：

| Outline 操作 | 级联状态 | Rearrange 行为 |
|-------------|---------|---------------|
| delete | `o_modified_deleted` | soft-delete 对应 pres slide |
| rename(modify_content=true) | `o_modified_modify` | 保留，content agent 重新生成 |
| insert(is_copy=true) | `o_modified_split` | 保留，content agent 重新生成 |
| delete(merge_id) | `o_modified_merge` | 保留，content agent 重新生成 |

---

## 7. Explore Agent

**文件**: `agent/outline/explore.py` (189 行)  
**入口**: `run_explore_agent(db, conversation_id, query?, file_ids?)`  
**调用方**: Master 的 `explore_knowledge` 工具

### 7.1 职责

探索知识文件 + 网络搜索，输出 JSON 格式的大纲结构建议（sections 划分 + 引用 file_id/chunk_id）。

### 7.2 工具集

| 工具 | 用途 | 调用上限 |
|------|------|---------|
| `search_knowledge` | BM25 检索知识库 | 12 次 |
| `search_web` | DuckDuckGo/SearXNG 网页搜索 | 8 次 (可关闭) |
| `fetch_web` | 抓取网页内容并入库 | 6 次 (可关闭) |
| `rebuild_index` | 重建 BM25 索引（fetch 新页面后） | 不限 |

### 7.3 输入构造

```
System Prompt: resources/prompts/outline/explore_system.md
User Prompt:
  ├── 用户需求 (query)
  ├── 文件摘要 (每个文件的 summary_json)
  └── 上次探索结果 (如果是修改模式，注入旧 explore_result)
```

### 7.4 输出

Agent 最终回复的纯文本（JSON 格式），写入 `outlines.explore_result_json`。后续 Generator 从中读取 file_id/chunk_id 构建知识上下文。

---

## 8. Outline Generator

**文件**: `agent/outline/generator.py` (258 行)  
**入口**: `run_outline_generator(db, conversation_id, section_id, query?, language?)`  
**调用方**: Master 的 `generate_outline_content` (并发 N 个 section) 或 `modify_outline_section` (单 section)

### 8.1 职责

为一个 section 的已有 slides 填充 `content_json`（主要观点、详细内容、数据、视觉建议、推荐格式）。

### 8.2 关键设计：无搜索工具

Generator **不拥有任何搜索工具**——这是与旧架构（Generator-Evaluator 循环中的 Generator 同时搜索和写大纲）的核心区别。知识内容通过以下链路注入：

```
Explore Agent → outlines.explore_result_json (file_ids + chunk_ids)
    ↓
Master 调用 generate_outline_content
    ↓
Generator._build_citation_knowledge(section)
    → 从 section.citations 读取 file_ids + chunk_ids
    → 从 DB 读取完整 chunk 文本
    → 拼接为 "## 知识库引用内容" 注入 user_prompt
```

### 8.3 工具集

| 工具 | 功能 |
|------|------|
| `write_slide` | 写入一个 slide 的 content_json（标题、要点、详细内容、数据、视觉建议、引用） |
| `pending_slides` | 查看当前 section 中还未写入的 slides |

### 8.4 Retry 机制

最多重试 `generator_max_retries` 次（配置项）。每次 retry 使用全新消息（不携带旧历史），注入当前进度：

```python
pending = await pending_slides.ainvoke({})
retry_msg = f"## 当前进度\n{pending}\n\n请继续逐个调用 write_slide 完成剩余的幻灯片。"
messages = [HumanMessage(content=user_prompt), HumanMessage(content=retry_msg)]
```

### 8.5 并发执行

`generate_outline_content` 通过 `asyncio.gather` 并发执行所有 section 的 Generator。每个 Generator 获得独立的 DB session（`get_session_manager().new_session()`），避免 async session 冲突。

完成后调用 `_finalize_special_slides()` 为 title/TOC/thanks 页自动生成层级 markdown 内容。

---

## 9. Style Agent

**文件**: `agent/ppt/style_agent.py` (247 行)  
**入口**: `run_style_agent(db, conversation_id)`  
**调用方**: Master 的 `ppt_style` 工具

### 9.1 职责

为 PPT 选择或创建配色/字号方案。如果 presentation 尚未创建，自动创建。

### 9.2 工具集

| 工具 | 功能 |
|------|------|
| `search_styles` | 按关键词搜索可用样式 |
| `get_style` | 获取样式完整详情 (colors, fonts, decoration, background) |
| `save_style` | 创建新样式并自动应用到 presentation |
| `set_presentation_style` | 应用已有样式到 presentation |

### 9.3 输入构造

User prompt 注入：
- 大纲标题
- 页数和页面类型分布（`{"content": 12, "section": 4, "title": 1, ...}`）
- 所有页面标题列表
- 背景指令参考 (从 `instruction/background.json` 加载)

### 9.4 闭包状态

使用 `list[int | None]` 闭包容器捕获结果（`_style_id`, `_rationale`, `_was_called`），因为 LangChain tool 函数必须返回字符串，无法直接修改外部变量。Agent 退出后通过闭包读取最终选择的 style_id。

---

## 10. Slide Agent

**文件**: `agent/ppt/slide_agent.py` (406 行)  
**入口**: `run_slide_agent(conversation_id, slide, style, template, query?, existing_outputs?, pres_status?, plan?)`  
**调用方**: `slides_content` / `modify_slides_content` 中的 `_write_slide_content()`

### 10.1 核心模型：Part-Based + Plan

Slide Agent 是 PPT 生成的最底层单元，每页 slide 独立运行一个 ReAct Agent。采用 Part-Based 模型——Agent 先规划页面分区，再逐区填充元素，最后标记完成。

```
submit_plan(parts=[{name, description, bounds}, ...])
    → 定义分区: "标题区", "内容区", "图表区", ...
    → 每个 part status = "pending"
    ↓
submit_background({type, color, ...})
    → 设置页面背景
    ↓
submit_element(element={type, position, ...}, part="内容区") × N
    → 每个元素经过: validator 校验 → decor_check → spatial_check
    → 元素归属到指定 part
    ↓
check_parts(part="内容区", complete=true)
    → 标记 part 完成
    ↓
Agent 退出条件: 所有 part 都 complete && 有 elements/background
```

### 10.2 工具集 (7 个)

| 工具 | 功能 | 类型 |
|------|------|------|
| `submit_plan` | 创建/更新 part 布局方案 | 核心 |
| `check_parts` | 查看进度 / 查看 part 元素 / 标记完成 | 核心 |
| `submit_element` | 添加/覆盖/删除元素 | 核心 |
| `submit_background` | 设置页面背景 | 核心 |
| `search_icons` | 搜索 Tabler Icons SVG | 辅助 |
| `read_instruction` | 读取元素类型使用说明 | 辅助 |
| `read_chart_instruction` | 读取图表类型使用说明 | 辅助 |

### 10.3 内存缓冲区

Slide Agent 纯内存操作，不访问 DB。所有状态存储在闭包捕获的 `_buffer` 字典中：

```python
_buffer = {
    "plan": {
        "design_concept": "现代科技风格",
        "parts": {
            "标题区": {"description": "...", "status": "pending", "bounds": {...}},
            "内容区": {"description": "...", "status": "complete"},
        }
    },
    "elements": {
        "a1b2c3d4": {"type": "textbox", "position": {...}, "_part": "标题区", ...},
        "e5f6g7h8": {"type": "chart", "position": {...}, "_part": "内容区", ...},
    },
    "background": {"type": "solid", "color": "F8FAFC"},
}
```

Agent 结束后，`_buffer` 序列化为 `{slide_index, elements, notes, background, plan}` 写入 `presentation_slides.agent_outputs`。

### 10.4 修改模式

当 `existing_outputs` 非空时进入修改模式：

1. 已有元素预加载到 `_buffer["elements"]`，保留 `_eid`
2. 已有 plan 的所有 part 状态为 `complete`
3. 保存 `_init_elements` / `_init_bg` 快照（崩溃恢复用）
4. Prompt 指导 LLM 流程：
   - `check_parts()` 查看现状
   - `submit_plan(parts=[需修改的 part])` → 重置为 pending
   - 修改元素
   - `check_parts(complete=true)` 标记完成

### 10.5 Retry 机制

最多 3 次重试。每次 retry 后检查退出条件（all parts complete + has content）：

| 场景 | 重试策略 |
|------|---------|
| 有部分进度（plan + 部分 elements） | 告知 LLM 当前状态，要求继续未完成的 part |
| 崩溃重置 | 恢复 `_init_elements` / `_init_bg` 快照，从头开始 |

### 10.6 元素提交检查链

每个 `submit_element` 调用经过四层检查：

```
① validate_elements() — JSON Schema 校验 (type, position 必需字段)
    ↓ 不通过 → 返回错误让 LLM 修正
② check_decor() — 装饰风格一致性 (emoji vs icon 二选一)
    ↓ 冲突 → 硬拒绝
③ check_element() — 空间检查 (越界/重叠/溢出)
    ↓ 问题 → 警告 (附带元素标签信息)
④ 写入 _buffer["elements"]
```

---

## 11. 质量检查体系

### 11.1 空间检查 (`ppt/spatial_check.py`, 276 行)

| 检查项 | 触发时机 | 级别 |
|--------|---------|------|
| 越界 | submit_element | ⚠ 警告 |
| 重叠 (非 shape) | submit_element, IoU > 30% | ⚠ 警告 |
| 重叠 (shape-shape) | submit_element, IoU > 30% | ℹ 提示 |
| 文字溢出 | submit_element (textbox) | ⚠ 警告 |
| Plan bounds 预检 | submit_plan | ⚠ 提示 |

重叠检测带 z_order 感知，元素标签格式：`eid[:8] (type:subtype, z=N)`

### 11.2 装饰检查 (`ppt/decor_check.py`, 102 行)

同一 slide 内 emoji 和 SVG icon 互斥。Plan 通过 `decor_style` 字段声明装饰策略，`submit_element` 时自动检测冲突。未声明时首次提交自动推断。

### 11.3 元素校验 (`ppt_engine/validator.py`, 252 行)

JSON Schema 校验每个元素的结构完整性：必需字段 (`type`, `position`)、类型特有字段 (`text_content` for textbox, `chart_data` for chart 等)。错误最多返回 10 条。

---

## 12. 数据流全景

### 12.1 完整 PPT 生成流程

```
用户: "帮我做一个关于 AI 的 PPT"
  │
  ▼ Master Agent 自行决策工具调用顺序:
  │
  ├─① get_conversation_status()    → 了解当前状态 (无大纲)
  ├─② create_empty_outline()       → 创建空大纲
  ├─③ explore_knowledge(query)     → [Explore Agent] 搜索 + 规划 sections
  ├─④ write_outline_structure()    → 写入 sections + slides 结构
  ├─⑤ generate_outline_content()   → [Generator × N] 并发填充所有 section 的 content_json
  ├─⑥ ppt_style()                 → [Style Agent] 选择配色方案, 创建 presentation
  ├─⑦ rearrange_presentation_slides() → 同步 presentation_slides
  └─⑧ slides_content()            → [Slide Agent × M] 并发生成每页 PPT 元素
      │
      └─ 每页 Slide Agent:
         submit_plan → submit_background → submit_element ×N → check_parts(complete)
         └→ 写入 presentation_slides.agent_outputs
  │
  ▼ Master 退出:
  ├─ 检测 outline_changed → 创建 outline_snapshot, 发送 document SSE
  ├─ 检测 presentation_changed → 创建 presentation_snapshot, 发送 document SSE
  └─ 返回 reply 文本
```

### 12.2 修改流程

```
用户: "把第 5 页的图表改成柱状图"
  │
  ▼ Master Agent:
  ├─① get_conversation_status()
  ├─② get_presentation()           → 查看当前 PPT slides 状态
  └─③ modify_slides_content(slide_ids=[5], modify_instructions={5: "柱状图"})
      │
      └─ Slide Agent (修改模式):
         existing_outputs 预加载 → check_parts() → submit_plan(重置待改 part)
         → submit_element(element_id=_eid, element={...}) → check_parts(complete)
```

### 12.3 大纲修改 → PPT 重排 → 选择性重生成

```
用户: "在第三章后面加一页讲数据分析"
  │
  ▼ Master Agent:
  ├─① modify_outline_structure(operations=[{op: "insert", after_id: 15}])
  │     → 创建新 outline_slide, reindex, cascade o_modified_* 到 pres slides
  ├─② modify_outline_section(section_id=3, query="新增数据分析页")
  │     → [Generator] 填充新 slide 的 content_json
  ├─③ rearrange_presentation_slides()
  │     → 删除 o_modified_deleted pres slides, 创建新 pres slides, reindex
  └─④ modify_slides_content(slide_ids=[新 slide ID])
        → [Slide Agent] 只生成新增/修改的页面
```
