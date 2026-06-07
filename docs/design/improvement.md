# PPTGenius 改进方案

> 版本: 0.2.0 | 日期: 2026-06-10

---

> 禁止在src、pptgenius目录及其上级目录新建任何文件夹或文件，除非在下表中明确列出。
> 所有文件必须经过静态测试，静态测试文件放在backen/src/tests目录下。

## 目录

- [PPTGenius 改进方案](#pptgenius-改进方案)
  - [目录](#目录)
  - [1. 系统架构总览](#1-系统架构总览)
  - [2. 统一 Master 工具规范](#2-统一-master-工具规范)
  - [3. 消息持久化](#3-消息持久化)
  - [4. 代码清理与目录重构](#4-代码清理与目录重构)
  - [5. Slide Agent 三工具模型](#5-slide-agent-三工具模型)
  - [6. Assembly 独立 + Notes 引用注入](#6-assembly-独立--notes-引用注入)
  - [7. 样式表简化](#7-样式表简化)
  - [8. Token 统计体系](#8-token-统计体系)
  - [9. 工具调用 Token 上限](#9-工具调用-token-上限)
  - [10. RAG 知识溯源与会话隔离](#10-rag-知识溯源与会话隔离)
  - [11. PPT 元素 z-order](#11-ppt-元素-z-order)
  - [12. 网络搜索开关 + Trim 监控](#12-网络搜索开关--trim-监控)
  - [13. 前端改进](#13-前端改进)
  - [14. DB 连接池（备选）](#14-db-连接池备选)
  - [15. 数据库变更汇总](#15-数据库变更汇总)
  - [16. 实施步骤](#16-实施步骤)

---

## 1. 系统架构总览

### 核心设计

**单一 Unified Master Agent。** 所有 sub-agent 作为 tool 平铺，产出直接写 DB，tool result 仅返回一行确认。

```
                  用户消息 (唯一入口)
                         │
                         ▼
              ┌─────────────────────┐
              │   Unified Master    │  System Prompt ~3.6k
              │   (单一 ReAct Agent) │  上下文峰值 ~14k
              └──────┬──────────────┘
                     │
     ┌───────────────┼───────────────┬──────────────────┐
     ▼               ▼               ▼                  ▼
  get_outline   outline_section  ppt_style         slides_content
  (读DB)        ×N 并行          (选样式)           (全页并行)
                     │               │                  │
                     ▼               ▼                  ▼
              outline_evaluate   写DB styles       Slide Agent ×N
              (评测)                              submit_element×8
                                                     │
                                                     ▼
                                                  写DB
                                                   │
                                                   ▼
                                               Assembly
                                             (infrastructure)
```

### Agent 及职责

| Agent | 角色 | 职责 |
|-------|------|------|
| **Unified Master** | 唯一入口 | 接收用户消息，自行写入大纲结构，调用 sub-agent tool，读写 DB 感知进度 |
| `get_outline` | tool (只读) | 返回 sections + slides 摘要（每页 title + main_points + 类型标记） |
| `outline_section` | tool (×N 并行) | 内部 search + fetch + ReAct 生成章节 slides，知识搜索完全隔离 |
| `outline_evaluate` | tool | 评测大纲，返回自然语言建议 |
| `ppt_style` | tool | 浏览 styles → 选一个 → 写 presentation |
| `slides_content` | tool | 内部 `asyncio.gather` N 个 Slide Agent 全并行 |
| **Assembly** | infra 函数 | z_order 排序 → 渲染 .pptx → snapshot，不经 LLM |

### 目标目录结构

> 原先的agent文件在agent_old中，写对应的文件**必须**查看对应的agent_old文件做参考

```
agent/
├── common/
│   ├── langchain_adapter.py
│   ├── token_middleware.py
│   └── model_builder.py
├── master.py                     # Unified Master (唯一入口)
├── master_prompts.py
├── tools/
│   ├── outline_section.py        # 内部含 search_knowledge + fetch_web
│   ├── outline_evaluate.py
│   ├── ppt_style.py
│   ├── slides_content.py         # 内部 asyncio.gather Slide Agent
│   └── slide_agent.py            # 三工具模型 (被 slides_content 调用)
└── ppt/
    ├── common/
    │   ├── instruction_loader.py
    │   └── tools.py              # search_icons, read_instruction
    └── slide_prompts.py

infrastructure/
├── ppt_engine/
│   ├── assembly.py
│   ├── exporter.py
│   ├── generator.py
│   └── parser/
└── ...
```

### 上下文对比

| | 旧架构（多 Graph） | 新架构（统一 Master） |
|---|---|---|
| 入口 | 3 层路由 | **1 个 Agent** |
| Master 上下文峰值 | ~40k | **~14k** |
| Knowledge 搜索 | 进 Agent 上下文 | **隔离**在 outline_section |
| Section/Slide 生成 | 进 Agent 上下文 | **隔离**在子 Agent |
| 并行性 | graph fan-out | 并行 tool_calls + asyncio.gather |
| 修改入口 | Coordinator 路由 | 自然语言，同一入口 |

---

## 2. 统一 Master 工具规范

### 设计原则

1. **`conversation_id` / `outline_id` 等由系统自动注入，LLM 不填写。** 参考当前工具格局（`_make_submit_slide_instruction` 中 `presentation_id` 和 `slide_index` 由闭包捕获）。
2. **Sub-agent 产出直接写 DB，tool result 仅返回一行确认。**
3. **Master 自行写入大纲结构**，保持全局感知。
4. **Conversation : Outline = 1:N，Outline : Presentation = 1:1。**

### 数据关系

```
conversations
  ├─ current_outline_id ──→ outlines(id)   ← 当前活跃大纲
  │
  ├─ outlines(id=12) ────→ presentations(id=5)   ← 1:1
  ├─ outlines(id=15) ────→ presentations(id=8)   ← 1:1
  └─ outlines(id=20) ────→ null                    ← 大纲未生成PPT
```

### 感知层（只读 DB，返回摘要。conversation_id / outline_id 自动注入）

---

**`get_conversation_status`**

```
入参: (无 — conversation_id 自动注入)
返回: {
  conversation_id: 1,
  current_outline_id: 12,
  outlines: [
    {id:12, title:"AI教育", version:"2.1.3", section_count:5, slide_count:18,
     status:"completed",
     presentation: {id:5, status:"completed", slide_count:18, style_id:3, file_path:"..."}},
    {id:15, title:"商业计划书", version:"1.0.0", section_count:3, slide_count:8,
     status:"draft",
     presentation: null},
  ],
  knowledge_files: [{id:1, filename:"AI白皮书.pdf", type:"pdf"}, ...]
}
~400t
用途: 任何操作前感知全局状态。current_outline_id 指向当前活跃的大纲
```

---

**`switch_outline`**

```
入参: outline_id: int | null
行为: UPDATE conversations SET current_outline_id = ?
返回: "已切换到大纲:'AI教育'(id=12, 18 slides, PPT已生成)"
     或 "已取消选中大纲" (outline_id=null 时)
~80t
用途: 用户说"切换到商业计划书那个大纲"时
```

---

**`get_outline`**

```
入参: (无 — 使用 current_outline_id)
      或 outline_id: int (显式指定)
返回: {
  id, title, version,
  sections: [{id,section_index,title,slide_count,
    slides: [{slide_index,id,title,
      summary: "main_points:[...], 2段落, has_chart"}]}]
}
~500-800t (18页)
```

---

**`get_outline_slide`** — 入参 `slide_id: int`，返回单页完整 content_json + citations，~500t。

**`get_presentation`** — 入参可选 `presentation_id`（默认从 current_outline 的 1:1 presentation 获取），返回每页 element_count + types 摘要，~400t。

**`get_knowledge_files`**

```
入参: (无 — conversation_id 自动注入)
返回: [
  {id:1, filename:"AI教育白皮书2024.pdf", type:"pdf", source_type:"upload",
   chunk_count:45,
   summary: {topics:["AI教育市场(§1-2)","核心技术(§3-4)","政策(§5)"],
             key_data:["500亿市场规模","45项政策","200+企业"]} | null,
   has_full_summary: true},
  {id:2, filename:"市场规模.xlsx", type:"xlsx", source_type:"upload",
   chunk_count:12,
   summary: null, has_full_summary: false},
]
~300-600t
summary 为 null 表示未生成 LLM 摘要，Master 可调用 summarize_file(id) 按需生成
```

**`list_styles`** — `[{id,name,label,colors,density}]`，~200t。

---

### 执行层（写 DB。conversation_id / outline_id 自动注入）

---

**`write_outline_structure`**

```
入参: {
  title: "AI教育发展报告",
  sections: [
    {section_index:1, title:"引言", description:"AI教育背景、发展历程、现状概览"},
    {section_index:2, title:"核心技术", description:"机器学习、NLP、计算机视觉"},
    {section_index:3, title:"应用案例", description:"K12、高等教育、职业教育"},
  ]
}
行为:
  1. 创建 outline + outline_sections (section_index 从 1 开始)
  2. 自动补全 title_slide (slide_index=1, layout_type="title")
     和 ending_slide (slide_index 最大, layout_type="thanks")
     → 插入到 outline_slides, 状态 pending, 待 outline_section 填充内容
  3. 自动设置 conversations.current_outline_id = 新 outline.id
  4. 不触发 LLM
返回: "已创建大纲:'AI教育发展报告'(id=12), 3 sections, title+ending 已自动添加" (~80t)

注意: title_slide 和 ending_slide 的 content_json 由 outline_section 填充,
      Master 规划 section 时不需要手动创建它们
```

---

**`modify_outline_structure`**

```
入参: {
  operations: [
    # ── 纯 DB 操作（不触发 LLM）──
    {op:"rename_slide", slide_index:5, new_title:"..."},
    {op:"delete_slide", slide_index:15},
    {op:"reorder_slides", section_index:2, slide_order:[5,7,6,8]},

    # ── 内容操作（仅占位，需后续 outline_section 填充）──
    {op:"merge_slides", slide_indices:[7,8], new_title:"..."},
    {op:"split_slide", slide_index:10},
    {op:"insert_slide", after_slide_index:4, section_index:1,
     title:"...", description:"..."},
  ]
}
行为:
  纯 DB 操作: 直接执行 (rename/delete/reorder)
  内容操作: 插入占位 record (content_json=null, status=pending)
            Master 必须在后续调用 outline_section 填充内容
  slide_index 从 1 开始，section_index 从 1 开始
返回: "完成: rename×1, merge×1(占位), delete×1。merge 的 slide 需调用 outline_section 填充"
     (~100t)

merge 操作流程:
  1. modify_outline_structure(op:"merge_slides", slide_indices:[7,8])
     → 创建新 slide (index=7, title="...", content_json=null, status=pending)
     → 标记 slide 7,8 为 deleted
  2. outline_section(section_id=2, regenerate_slides=[7], knowledge_mode="refresh")
     → 子 Agent 搜索知识 + 填充新 slide 7 的 content_json
```

---

**`summarize_file`**

```
入参: {file_id: int}
内部: 子 Agent (轻量, ~5-8k)
  1. 采样 chunks: 前2 + 后1 + 均匀采样N个 (覆盖全文, 避免只看开头)
  2. 生成结构化摘要
  3. 写 knowledge_files.summary_json (缓存, 后续 get_knowledge_files 直接返回)
  4. 返回摘要
返回: {
  file_id: 1,
  topics: ["AI教育市场分析(§1-2)", "核心技术架构(§3-4)", "政策与合规(§5)"],
  key_data: ["2024市场规模:500亿", "45项国家级政策", "200+AI教育企业"],
  suggested_sections: [         # 可选: 给 Master 的 section 拆分建议
    {title:"市场背景", source_range:"§1-2", knowledge_file_id:1},
    {title:"技术原理", source_range:"§3-4", knowledge_file_id:1},
    {title:"政策环境", source_range:"§5",   knowledge_file_id:1},
  ]
}
~400t
调用时机:
  - 文件上传 + 索引完成后自动触发 (异步, 后台)
  - get_knowledge_files 返回 summary=null 时 Master 按需调用
  - 缓存命中则直接返回, 不重复调用 LLM
与对话 summarize 共用 SummaryAgent 基类, 仅 prompt 不同
```

---

**`outline_section`**

```
入参: {
  query: str | null,
  section_id: int,
  topic: "核心技术: ML, NLP, CV",
  knowledge_hint: "重点参考: AI白皮书(id=1), 市场规模(id=2)",
  knowledge_mode: "auto"|"reuse"|"refresh"|"extend",
  regenerate_slides: null | [global_slide_index, ...],
}
内部: 子 Agent (system ~2k)
  search_knowledge(≤12) + search_web(≤8) + fetch_web(≤6)
  ReAct ~30-50k 完全隔离 → write_outline_slides 写 DB
  生成的 slides 在 section 内部编号为 1..N
返回: "Section 2'核心技术'完成: 4 slides, citations=[1,2,3]" (~80t)
```

**并行生成后的全局索引重排：**

每个 `outline_section` 独立生成，不知其他 section 的页数。全部返回后系统按 section 顺序逐页递增分配全局 slide_index：

(只有当 `regenerate_slides` 不为 null 时才触发重排，避免修改重排导致混乱)

```
write_outline_structure 创建:
  slide_index=1  title_slide   (占位)
  slide_index=?  ending_slide  (占位, 最大 index 待定)

outline_section ×3 并行:
  Section 1 "引言"     → 内部 1..3: [概述, 历程, 现状]
  Section 2 "核心技术" → 内部 1..4: [ML基础, NLP, CV, 框架]
  Section 3 "应用案例" → 内部 1..2: [K12案例, 高教案例]

全部返回后, 系统逐 section 重排:
  slide_index=1  title_slide
  slide_index=2  Section 1 概述
  slide_index=3  Section 1 历程
  slide_index=4  Section 1 现状
  slide_index=5  Section 2 ML基础
  slide_index=6  Section 2 NLP
  slide_index=7  Section 2 CV
  slide_index=8  Section 2 框架
  slide_index=9  Section 3 K12案例
  slide_index=10 Section 3 高教案例
  slide_index=11 ending_slide

outline.slide_count = 11, ending_slide 置为 index=11
```

---

**`outline_evaluate`**

```
入参: {query: str | null}
      # 用户有具体评测要求时填写，如"重点看数据完整性"
      # 无要求则为 null → 全面评测
内部: 子 Agent 读全量 outline + query → 评测 → 写 eval_detail
返回: {
  overall: 7.5,
  suggestions: [
    "Slide 3 内容过少，建议补充数据",
    "Section 2 布局单一，slide 5 建议 two_column"
  ]
}
~300t
```

---

**`ppt_style`**

```
入参: {query: str | null}
      # 用户有具体风格要求时由 Master 填写，如"换成科技深色风格"
      # 无要求则为 null → Agent 根据大纲主题自主判断
自动注入: current_outline_id → 读取大纲摘要
内部: 子 Agent 收到:
  - query (用户风格要求, 可为空)
  - outline_summary (主题、领域、章节列表)
  - 可用 styles 列表
  - 当前 presentation 的 style (如果已有, 修改场景)
  行为:
    1. 如有 query → 按用户要求定向选择或创建
    2. 如无 query → 根据大纲主题和领域自主判断风格方向
    3. 浏览 styles → 选或创 → 写 presentations.style_id
  System Prompt 参考当前 style_agent (list_color_schemes + get_color_scheme + save_color_scheme)
返回: "已选:'商务蓝'(id=3, primary=#1a56db, density=moderate)" (~80t)
     或 "已创建新样式:'科技深蓝'(id=7) 并应用" (~60t)
```

---

**`slides_content`**

```
入参: {
  query: str | null,
  # 用户有具体修改要求时由 Master 填写，如"全部页背景改为深色"
  # 无要求则为 null → 全新生成
  slides: [{slide_index, outline_slide_id, title, layout_hint}, ...]
         # 不传则从 current_outline 的全部 slides 生成
  modify_instructions: null | {5:"柱状图→饼图", 7:"背景深色"},
}
自动注入:
  - presentation_id (从 current_outline 的 1:1 presentation)
  - style: {id, colors:{primary,accent,...}, fonts:{title,body,...}, background_json, density}
  - template: {slide_width, slide_height, layouts_json}  ← 预设模板，LLM 参考但不强制遵守
内部: asyncio.gather ×N Slide Agent
  每页 System Prompt 注入:
    - style 的 color/font/background 具体值 (~500t)
    - template 的布局预设 (参考用, ~300t)
    - z_order 参照表
    - 三工具: submit_element + submit_notes + submit_background
  ReAct 8-12轮, ~40-60k 完全隔离
  结束一次性写 DB: agent_outputs={elements,notes,background}
返回: "15/15 完成, 0 失败" (~50t)
```

---

### 导出层（不经 LLM）

- **`assembly`** — 读 slides → z_order 排序 → 渲染 .pptx → snapshot，返回 file_path (~50t)
- **`export_outline`** — `(format, version)` → 导出，返回 file_path (~50t)

---

### Master System Prompt ~3.6k tokens

领域知识全在 sub-agent 的 prompt 里。Master 只描述流程编排。

### 上下文增长（新生成 4 sections, 15 slides）

```
Round 0:  System(3.6k) + User(0.3k)                         =  3.9k
Round 1:  get_conversation_status → 400t                     =  5.1k
Round 2:  write_outline_structure → 60t                      =  5.8k
Round 3:  outline_section ×4 并行 → 320t                     =  6.8k
Round 4:  get_outline → 600t                                 =  8.0k
Round 5:  outline_evaluate → 300t                            =  8.9k
── 用户确认 ──
Round 6:  ppt_style → 80t                                    =  9.6k
Round 7:  slides_content → 50t                               = 10.3k
Round 8:  assembly → 50t                                     = 11.0k

峰值: 11.0k + reasoning(8轮×1k) ≈ 19k
```

### 信息不丢失策略

| 场景 | 保证方式 |
|------|---------|
| 新对话/重载 | `get_conversation_status` 返回所有 outline + presentation 状态 |
| 切换大纲 | `switch_outline` → `get_outline` 读取结构 |
| ppt_style 需要上下文 | 自动注入 outline 摘要（主题、领域、章节列表） |
| slides_content 需要 style | 自动注入 style 完整值 + template 预设 |
| 修改前 | `get_outline_slide` 读单页完整 content_json |
| 所有 agent 调用 | `agent_id`（内存）追踪，token cost 写入 `messages.token_cost_json` |

### Snapshot 记录时机

**Master 退出时（每次用户消息处理完毕），检查 outline 和 presentation 是否发生变更：**
可以通过state bool量实现

```
Master 处理完用户消息
  │
  ├─ outlines 有变更 (新增/修改)?
  │   → export_outline_snapshot(current_outline_id)
  │   → 写入 outline_snapshots
  │
  └─ presentations 有变更 (新增/修改)?
      → export_presentation_snapshot(current_presentation_id)
      → 写入 presentation_snapshots
```

变更检测：比较处理前后的 `updated_at` 或标记位。不检测则跳过，不产生冗余快照。

### 子 Agent 内部工作流

**`summarize_file`**

```
入参: {file_id}
       │
       ▼
  System Prompt (~1k): 文件摘要规则 (与对话 summarize 共用 SummaryAgent 基类)
       │
  ┌────┴────┐
  │ ReAct   │  采样 chunks: 前2 + 后1 + N个均匀采样
  │ ~5-8k   │  读取 → 提取主题/关键数据/建议section
  │ (隔离)   │  写 knowledge_files.summary_json (缓存)
  └────┬────┘
       │
       ▼
  返回: {topics:[...], key_data:[...], suggested_sections:[...]}
```

**`outline_section`**

```
入参: {query, section_id, topic, knowledge_hint, knowledge_mode, regenerate_slides}
       │
       ▼
  System Prompt (~2k): 大纲生成规则 + 工具列表
       │
  ┌────┴────┐
  │ ReAct   │  search_knowledge (≤12次) ──→ BM25 知识库
  │ ~30-50k │  search_web (≤8次)         ──→ DuckDuckGo
  │ (隔离)   │  fetch_web (≤6次)          ──→ 抓取+索引
  │         │  write_outline_slides       ──→ DB (outline_slides + citations)
  └────┬────┘
       │
       ▼
  返回: "Section 2 完成: 4 slides, citations=[1,2,3]"
```

**`outline_evaluate`**

```
入参: {query}
       │
       ▼
  System Prompt (~1k): 评测维度 + 输出格式
       │
  ┌────┴────┐
  │ ReAct   │  读全量 outline (DB)
  │ ~10-15k │  逐 slide 评测
  │ (隔离)   │  写 eval_detail → DB
  └────┬────┘
       │
       ▼
  返回: {overall: 7.5, suggestions: [...]}
```

**`ppt_style`**

```
入参: {query}
       │
       ▼
  自动注入: outline_summary + styles 列表
       │
  ┌────┴────┐
  │ ReAct   │  list_styles (浏览)
  │ ~5-10k  │  get_style (查看详情)
  │ (隔离)   │  [save_style] (创建, 可选)
  │         │  set_presentation_style → DB
  └────┬────┘
       │
       ▼
  返回: "已选:'商务蓝'(id=3)" 或 "已创建并应用(id=7)"
```

**`slides_content` → 内部 Slide Agent**

```
入参: {query, slides[], modify_instructions, style, template}
       │
       ▼
  自动注入: style 完整值 + template 预设 + z_order 参照表
       │
  ┌────┴──────────────────┐
  │ asyncio.gather ×N      │
  │  ┌──────────────────┐  │
  │  │ Slide Agent (×N) │  │
  │  │ System (~4.7k)    │  │
  │  │ ReAct 8-12轮      │  │
  │  │ ~40-60k each      │  │
  │  │ submit_element ×8 │  │
  │  │ submit_notes      │  │
  │  │ submit_background │  │
  │  │ [delete_element]  │  │
  │  │ → 结束一次性写DB   │  │
  │  └──────────────────┘  │
  └────┬──────────────────┘
       │
       ▼
  返回: "15/15 完成, 0 失败"
```

### 操作分类与调用规则

| 操作 | 类型 | 是否需要 LLM | 后续动作 |
|------|------|------------|---------|
| `rename_slide` | 纯 DB | 否 | — |
| `delete_slide` | 纯 DB | 否 | — |
| `reorder_slides` | 纯 DB | 否 | — |
| `merge_slides` | 占位 | 需填充 | `outline_section(regenerate_slides=[...])` |
| `split_slide` | 占位 | 需填充 | `outline_section(regenerate_slides=[...])` |
| `insert_slide` | 占位 | 需填充 | `outline_section(regenerate_slides=[...])` |

**索引规则：所有 `slide_index` 和 `section_index` 从 1 开始。**

### 典型调用链路

```
新建大纲:
  write_outline_structure({title, sections})
    → title_slide(index=1) + ending_slide 已自动补全
  outline_section ×N 并行 → 填充所有 section (含 title/ending)

结构修改:
  modify_outline_structure({op:"rename_slide", slide_index:5, ...})
    → 纯 DB, 完成

内容修改:
  modify_outline_structure({op:"merge_slides", slide_indices:[7,8], ...})
    → 占位 slide 已创建, status=pending
  outline_section(section_id=2, regenerate_slides=[7], knowledge_mode="refresh")
    → 子 Agent 填充内容

单页内容修改 (不改结构):
  outline_section(section_id=2, query="第5页补充数据案例", regenerate_slides=[5])

PPT 单页修改:
  slides_content(query="柱状图→饼图", modify_instructions={5:"柱状图→饼图"})
```

---

## 3. 消息持久化

### 3.1 原则

**Master 的 tool_calls 和 tool_results 必须成对持久化到 `messages` 表。** 这是正确性要求，不是可选项。

### 3.2 原因

1. **LangChain 消息完整性：** 重载对话时，tool_calls 和 tool_results 必须成对出现。如果只持久化 tool_calls 而丢失 tool_results，会出现 dangling tool_calls → API 400 错误。
2. **上下文延续：** 持久化后 Master 不需要每次对话重新"认识"项目（避免额外 2-3 轮 `get_project_status` + `get_outline`）。
3. **Token 代价可忽略：** 新架构 tool result 全是 ~50-300t 摘要，全流程 ~15 条 tool messages ≈ 2,000t。DeepSeek 1M 上下文完全容纳。
4. **Summarize 兜底：** 长对话时压缩旧轮次，不会无限膨胀。

### 3.3 存储格式

`messages` 表已有 `metadata_json JSON` 列，tool 消息通过 `content_type` + `metadata_json` 区分：

```sql
-- messages 表已有结构
content_type VARCHAR(32) DEFAULT 'text'
  -- 'text'       — 用户/AI 可见消息
  -- 'tool_call'  — Master 调用 sub-agent（前端过滤，不展示）
  -- 'tool_result'— sub-agent 返回结果（前端过滤）
  -- 'system'     — 系统消息
```

前端渲染时过滤 `content_type IN ('tool_call', 'tool_result')`，不显示在聊天界面。Summarize 时按 `tool_call → tool_result` 成对压缩为一行摘要。

### 3.4 DeepSeek reasoning_content 要求

DeepSeek V4 Thinking Mode 的 `reasoning_content` 必须在多轮 tool calling 中原样传回，否则 API 返回 400。这由 `langchain_adapter.py` 的两个 patch 保证：

```
Patch 1 (_create_chat_result):
  API 响应中的 reasoning_content → AIMessage.additional_kwargs["reasoning_content"]

Patch 2 (_convert_message_to_dict):
  AIMessage.additional_kwargs["reasoning_content"] → API 请求的 reasoning_content 字段
```

**持久化时：** AIMessage 的 `additional_kwargs` 随消息序列化一起存入 `messages.content` / `metadata_json`。重载对话时反序列化恢复 `additional_kwargs`，patch 2 自动将其注入回 API 请求。

**message 存储时额外处理：** 如果使用 LangChain 的 `messages_to_dict` / `messages_from_dict` 序列化，`reasoning_content` 保存在 `additional_kwargs` 中自然跟随。如果自定义序列化（如只存 `content` 文本），则需要显式保存 `additional_kwargs` 到 `metadata_json`：

```python
# 写入 message 时
if isinstance(msg, AIMessage) and msg.additional_kwargs.get("reasoning_content"):
    metadata["reasoning_content"] = msg.additional_kwargs["reasoning_content"]

# 重载 message 时
if metadata.get("reasoning_content"):
    aimsg = AIMessage(content=content, additional_kwargs={"reasoning_content": metadata["reasoning_content"]})
```

### 3.5 持久化时机

与 token cost 写入时机一致——Agent return 前、AIMessage 写入 `messages` 表时一并处理。

---

## 4. 代码清理与目录重构

### 删除

| 路径 | 原因 |
|------|------|
| `agent/ppt/phase2_sub_agent/` | 多 Agent 管线，已弃用 |
| `agent/ppt/phase2_freedom/` | Freedom 管线，已弃用 |
| `agent/ppt/phase2_super_freedom/` | → `tools/slide_agent.py` + `ppt/slide_prompts.py` |
| `agent/ppt/phase1_style.py` | → `tools/ppt_style.py` |
| `agent/ppt/common/layout_resolver.py` | `select_layout` 内联 |
| `agent/ppt/layout/definitions.py` | 对应 JSON 在 resources/layouts/ |
| `agent/outline/middleware.py` | → `agent/common/token_middleware.py` |
| `agent/outline/graph.py` | 无 Graph 编排 |
| `agent/ppt/graph.py` | 无 Graph 编排 |
| `agent/ppt/dispatcher.py` | → `tools/slides_content.py` 内部 asyncio.gather |
| `agent/coordinator.py` | → `agent/master.py` |
| `infrastructure/db/repository/template.py` | templates 表删除 |
| dispatcher retry loop | 删除 |
| slide_agent validation retry | 删除 |
| `increment_slide_retry*` | 删除 |
| `frontend/src/**/*.js` (5个) | 与 .ts 重复，导致热重载失效 |

### 新增

| 路径 | 用途 |
|------|------|
| `agent/master.py` | Unified Master Agent |
| `agent/master_prompts.py` | Master system prompt |
| `agent/tools/outline_section.py` | 章节大纲生成（含知识搜索） |
| `agent/tools/outline_evaluate.py` | 大纲评测 |
| `agent/tools/ppt_style.py` | 样式选择 |
| `agent/tools/slides_content.py` | 全页并行生成 |
| `agent/tools/slide_agent.py` | 单页生成（三工具模型） |
| `agent/common/token_middleware.py` | TokenCountingMiddleware（双层写） |
| `agent/common/model_builder.py` | 统一 LLM 构建 + agent_id |
| `infrastructure/ppt_engine/assembly.py` | 独立 assembly 函数 |
| `infrastructure/ppt_engine/exporter.py` | 快照导出 |

---

## 5. Slide Agent 三工具模型

### 四工具

| 工具 | 模式 | 说明 |
|------|------|------|
| `submit_element` | **增写** | 先validate，每个 element 自动分配 `id`（randint 8位 hex），缓存内存 |
| `submit_notes` | **覆写** | 设置 speaker notes |
| `submit_background` | **覆写** | 设置背景 |
| `delete_element` | **删除** | 按 id 从内存列表删除 |

Agent 结束时一次性写 DB：`agent_outputs = {elements, notes, background}`（无外层 super_freedom key）。

修改元素 = `delete_element(id)` + `submit_element(new_element)`。

注意引导agent思考元素之间的层级关系（z-order）以及元素布局问题。

### System Prompt 提示

```
设计完成后 slide 自动提交。element 逐个添加。
修改元素时先 delete 再 submit。
z_order 参照:
  0=背景 10=背景图 20=大装饰 30=图片 40=图表 50=表格
  60=小装饰 70=正文 80=标题 90=页码
```

---

## 6. Assembly 独立 + Notes 引用注入

### assembly.py（infrastructure/ppt_engine/）

```
assemble_pptx(db, presentation_id, conversation_id, user_id) → file_path
  1. 读取 presentation_slides.agent_outputs
  2. 读取 outline_slides.citations → 查询 knowledge_files
  3. 每页: elements 按 z_order 排序 → 顺序添加（后加=上层）
  4. 每页: Agent notes + 增写引用:
     参考来源:
     [1] AI教育白皮书2024.pdf
     [2] https://example.com/ai-edu-trends
  5. 渲染 .pptx + 导出 snapshot
```

### 调用路径

- Graph 结束时调 `assemble_pptx`
- `POST /api/presentations/{id}/reexport` 直接调 `assemble_pptx`（不经 LLM）

---

## 7. 样式表简化

- **删除 `templates` 表**（布局存 `resources/layouts/*.json`）
- **`color_schemes` → `styles`**，新增 `background_json`
- 删 `template_id` 列（presentations + presentation_slides）
- `color_scheme_id` → `style_id`

---

## 8. Token 统计体系

### 双层计数器

Token 统计在内存中维护两层：
- `TokenCounter._conv_counters: dict[int, TokenCounter]` — 按 conversation_id
- `TokenCounter._agent_counters: dict[str, TokenCounter]` — 按 agent_id（内存 key，不持久化）

`agent_id` 由 `model_builder` 随机生成（`secrets.token_hex(4)`），仅作为内存中 TokenCounter 的 key，不存入数据库。

### Cost 归属

Token cost 统一记录在 `messages` 表：

| 消息类型 | content_type | token_cost_json 写入时机 |
|---------|-------------|------------------------|
| Master 普通回复 | `text` | Middleware `after_model` |
| Tool 调用结果 | `toolresult_slide` / `toolresult_outline_section` 等 | Tool 返回时写入对应消息行 |
| 用户消息 | `text` | 无（不计费） |

`messages` 表保留原有 `estimated_cost DOUBLE`（美元计费），新增 `token_cost_json JSON`（token 数量明细 `{input, output, total}`）。

### Middleware 写入

```python
class TokenCountingMiddleware(AgentMiddleware):
    def __init__(self, message_id: int, agent_id: str):
        self.message_id = message_id
        self.agent_id = agent_id

    def after_model(self, state, runtime):
        usage = state.get("usage", {})
        tc_conv = TokenCounter.for_conversation(conv_id)
        tc_agent = TokenCounter.for_agent(self.agent_id)
        tc_conv.add(usage); tc_agent.add(usage)
        # 异步写入 messages.token_cost_json
        db.update_message_token_cost(self.message_id, usage)
```

Middleware 需要拿到 `message_id`（create_message 返回的 ID），在 `after_model` 中累加写入。

如果 middleware 中拿不到 message_id，则在 tool 调用结束时直接调用 `update_message_token_cost` 修改 DB。因为 token cost 只需累加，只需提供累加接口。

---

## 9. 工具调用 Token 上限

### 单次工具输出

| 工具 | 输出量 | Token | 依据 |
|------|--------|-------|------|
| `search_knowledge` | `[score] <500 chars>` ×5 | ~2,000 | generator.py:69 |
| `search_web` | title+URL+snippet ×5 | ~600 | snippet 100-200 chars |
| `fetch_web` | 元数据 + text[:1000] | ~500 | generator.py:186 |
| `read_file` | 全 chunk → [:8000] | ~4,000 | generator.py:133 |

### 安全上限（子 Agent 独占 1M 上下文，预算充裕）

子 Agent 是专用 Agent，无外层并发上下文压力，上限可以较高：

| 工具 | 上限 | 超出返回 |
|------|------|---------|
| `fetch_web` | **6** | "抓取已达上限(6次)" |
| `read_file` | **5** | "读取已达上限(5次)" |
| `search_knowledge` | **12** | "搜索已达上限(12次)" |
| `search_web` | **8** | "搜索已达上限(8次)" |
| **单 Agent 总调用** | **24** | — |

不限制 ReAct 轮数，但所有工具的 system prompt 末尾注入次数限制。

### Trim 监控

所有 `trim_max_tokens` 触发 WARNING：`"Context trimmed: X → Y tokens (threshold=Z)"`

---

## 10. RAG 知识溯源与会话隔离

### 溯源

`outline_slides.citations` 存 `[{knowledge_file_id}]` 数组。

`knowledge_files` 新增 `web_url` + `conversation_id`。

Assembly 阶段根据 `knowledge_file_id` 查询 `filename` / `web_url`，增写到 slide notes。

### 双索引

- **全局**：`BM25Index`（`conversation_id IS NULL`）
- **会话**：`BM25Index(conversation_id)`
- 前端搜索面板 Switch `[全局] [当前会话]`

---

## 11. PPT 元素 z-order

### 原理

python-pptx 越晚添加越靠上。Assembly 中 `sorted(elements, key=z_order)` 升序排列后顺序添加。

**不修改 parser。** 在 assembly.py 排序即可。

### 参照表（注入 slide_prompts）

| z_order | 元素 |
|---------|------|
| 0 | background |
| 10 | background_image / background_shape |
| 20 | large_shape |
| 30 | picture/icon |
| 40 | chart |
| 50 | table |
| 60 | small_shape / small_icon |
| 70 | textbox body |
| 80 | textbox title |
| 90 | page_number |

---

## 12. 网络搜索开关 + Trim 监控

- `OutlineState.web_search_enabled: bool`，默认 `True`
- 前端 Chat 面板 Switch `[网络搜索]`
- `False` 时从 outline_section 子 Agent 移除 `fetch_web` / `search_web`
- 所有 `trim_max_tokens` 操作 WARNING 日志

---

## 13. 前端改进

| # | 改进 | 说明 |
|---|------|------|
| 1 | JS/TS 冲突 | 删除 5 个冗余 `.js` 文件 |
| 2 | 拖拽上传 | Chat 输入区支持拖拽，drop zone 高亮 |
| 3 | 文件数量限制 | 修复 `max_count` 绑定 |
| 4 | 等待动画 | 骨架屏 + 进度文字（"正在搜索知识库..."、"正在生成第3页..."） |
| 5 | 记住我 | `localStorage`(7天) vs `sessionStorage`，token 自动刷新 |
| 6 | 网络搜索开关 | Chat 面板 Switch `[网络搜索]`，状态传 Master |

---

## 14. DB 连接池（备选）

保持 `pool_size=25, max_overflow=25`。事件队列方案（Agent → Queue → 单连接 Writer）可行但不紧急。

---

## 15. 数据库变更汇总

当前 DB 为空，直接修改 `schema.sql` 重新建表。

### 新增表

| 表 | 用途 |
|-----|------|
| `outline_sections` | 章节 + chunk 绑定 + token计费 |
| `outline_snapshots` | 大纲版本快照 |

### 删除表

| `templates` |

### 重命名

| 原 | 新 |
|----|-----|
| `color_schemes` | `styles` |

### 新增列

| 表 | 列 | 类型 |
|-----|-----|------|
| `conversations` | `current_outline_id` | INT FK → outlines |
| `messages` | `token_cost_json` | JSON（token 明细） |
| `styles` | `background_json` | JSON |
| `outlines` | `version_major/minor/patch` | INT（替代旧 version INT） |
| `outlines` | `eval_detail` | JSON |
| `outline_sections` | （整表新增） | |
| `outline_slides` | `section_id` | INT FK → outline_sections |
| `outline_slides` | `citations` | JSON |
| `outline_slides` | `status` | VARCHAR(32) DEFAULT 'pending' |
| `outline_snapshots` | （整表新增） | |
| `knowledge_files` | `web_url` | VARCHAR(2048) |
| `knowledge_files` | `conversation_id` | INT + INDEX |
| `knowledge_files` | `summary_json` | JSON |

### 删除列

| 表 | 列 |
|-----|-----|
| `outlines` | `version` INT（→ version_major/minor/patch） |
| `outline_slides` | `agent_id` |
| `presentations` | `template_id` |
| `presentations` | `agent_id` |
| `presentation_slides` | `template_id` |
| `presentation_slides` | `agent_id` |
| `presentation_slides` | `color_scheme_id` → `style_id` |

> **注意：** `agent_id` 不存入任何表，仅作为内存中 TokenCounter 的 key。`token_cost_json` 仅存在于 `messages` 表，大纲/PPT 各表不存。

---

## 16. 实施步骤

### 文件规模约束

| 约束 | 值 |
|------|-----|
| 单个 `.py` 文件 | ≤ 300 行 |
| 单个函数 | ≤ 60 行 |
| 每文件职责 | 单一主题 |

当前超标文件（需拆分）：`coordinator.py`(648行)、`generator.py`(333行)、`phase1_style.py`(333行)。

---

### Phase 0: DB Schema（1 文件，~250行）

**目标：** 新 schema.sql 覆盖所有表变更，models.py 同步。

| # | 任务 | 文件 | 行 | 内容 |
|---|------|------|-----|------|
| 0.1 | 重写 schema.sql | `resources/schema.sql` | ~250 | 删 templates，重命名 color_schemes→styles，新增 outline_sections/outline_snapshots，所有新增列 |
| 0.2 | 更新 ORM models | `infrastructure/db/models.py` | ~260 | 删 Template，ColorScheme→Style，新增 OutlineSection/OutlineSnapshot，已有表加新列 |
| 0.3 | 更新 seed.py | `infrastructure/db/seed.py` | ~80 | 只 seed styles（从 resources/color_schemes/ 读取，加 background_json） |
| 0.4 | 删 template repository | 删除 `infrastructure/db/repository/template.py` | — | 功能合并到 style repository |
| 0.5 | 更新 database.py facade | `infrastructure/db/database.py` | ~130 | 删 template 方法，加 style 方法，加 conversation.current_outline_id 读写 |

---

### Phase 1: Common 基础设施（3 文件）

**目标：** Token 统计 + LLM 构建 + DeepSeek 适配，全 Agent 共用。

| # | 任务 | 文件 | 行 | 内容 |
|---|------|------|-----|------|
| 1.1 | TokenCounter 扩展 | `infrastructure/utils/token_counter.py` | ~220 | 新增 `_agent_counters: dict[str, TokenCounter]`，新增 `for_agent(agent_id)`，新增 `get_cost(key: int\|str)` 双接口 |
| 1.2 | TokenCountingMiddleware | `agent/common/token_middleware.py` | ~60 | 从 `outline/middleware.py` 移出，`after_model` 同时写 conv + agent 两层计数器，接受 `agent_id` 参数 |
| 1.3 | Model builder | `agent/common/model_builder.py` | ~80 | `build_llm(conversation_id) → (llm, agent_id, middleware)` — 自动装配 config 参数，生成 `agent_id`（`secrets.token_hex(4)`），附加 TokenCountingMiddleware |

---

### Phase 2: Master Agent（3 文件，总计 ~500行）

**目标：** 单一入口 Agent，工具定义 + 路由逻辑 + prompt。

| # | 任务 | 文件 | 行 | 内容 |
|---|------|------|-----|------|
| 2.1 | Master system prompt | `agent/master_prompts.py` | ~120 | `build_master_system_prompt()` — 4 段结构（角色/工作流/knowledge_mode/修改策略），~3.6k tokens |
| 2.2 | 感知层工具（7 个） | `agent/tools/perception.py` | ~280 | `get_conversation_status`, `switch_outline`, `get_outline`, `get_outline_slide`, `get_presentation`, `get_knowledge_files`, `list_styles` — 全部只读 DB，返回摘要。conversation_id/outline_id 闭包注入 |
| 2.3 | 结构工具（2 个） | `agent/tools/structure.py` | ~180 | `write_outline_structure`（含 title+ending 自动补全），`modify_outline_structure`（纯DB操作 + 占位操作分离） |
| 2.4 | Master agent entry | `agent/master.py` | ~280 | `run_master_agent()` — 组装工具列表，`create_agent(model, tools, system_prompt, middleware)`，`recursion_limit=25`。所有工具闭包注入 conversation_id/outline_id。含 Snapshot 记录逻辑（退出时检查变更） |

---

### Phase 3: Outline 子 Agent（3 文件，总计 ~650行）

**目标：** 章节生成 + 评测 + 文件摘要，每个子 Agent 作为独立 tool。

| # | 任务 | 文件 | 行 | 内容 |
|---|------|------|-----|------|
| 3.1 | outline_section agent | `agent/tools/outline_section.py` | ~280 | 入参 `{query, section_id, topic, knowledge_hint, knowledge_mode, regenerate_slides}`。内部: build system prompt(~2k) + 工具: `search_knowledge`(≤12), `search_web`(≤8), `fetch_web`(≤6), `read_file`(≤5), `write_outline_slides`。ReAct 生成 → 写 outline_slides + citations → 返回一行确认。section 内部 slide 编号 1..N，全局重排由调用方处理 |
| 3.2 | outline_evaluate agent | `agent/tools/outline_evaluate.py` | ~180 | 入参 `{query}`。内部: 读全量 outline → 按维度评测 → 写 `outlines.eval_detail`。返回自然语言 `{overall, suggestions[]}`。不限建议条数 |
| 3.3 | summarize_file agent | `agent/tools/summarize_file.py` | ~190 | 入参 `{file_id}`。内部: 采样 chunks（前2+后1+N均匀）→ 提取 topics/key_data/suggested_sections → 写 `knowledge_files.summary_json`（缓存）。与对话 summarize 共用 `SummaryAgent` 基类（prompt 不同）。文件上传后异步触发 |

---

### Phase 4: PPT 子 Agent（4 文件，总计 ~850行）

**目标：** 样式选择 + 全页并行生成 + 单页三工具模型。

| # | 任务 | 文件 | 行 | 内容 |
|---|------|------|-----|------|
| 4.1 | Slide Agent 三工具 | `agent/tools/slide_agent.py` | ~250 | `submit_element`(增写, 自动 randint id), `submit_notes`(覆写), `submit_background`(覆写), `delete_element`(按id删)。内存缓存 `_buffer = {elements:[], notes:"", background:{}}`，Agent 结束一次性写 DB `agent_outputs`。modify 场景先读现有 agent_outputs |
| 4.2 | Slide prompts | `agent/ppt/slide_prompts.py` | ~180 | `build_slide_system_prompt(style, template, z_order_table)` — 注入 style 完整值 + template 预设(参考) + z_order 参照表 + 工具列表。从 `resources/prompts/ppt/` 加载模板 |
| 4.3 | slides_content tool | `agent/tools/slides_content.py` | ~250 | 入参 `{query, slides[], modify_instructions}`。自动注入 style + template。内部: `asyncio.gather` ×N Slide Agent（每个独立 ReAct ~40-60k），全部完成后返回汇总。通过 `get_stream_writer` 推送中间 SSE 事件 |
| 4.4 | ppt_style agent | `agent/tools/ppt_style.py` | ~170 | 入参 `{query}`。自动注入 outline_summary。内部: `list_styles` + `get_style` + 可选 `save_style`(创建新样式)。参考当前 style_agent prompt。选或创后写 `presentations.style_id` |

---

### Phase 5: Assembly + Exporter（2 文件，总计 ~400行）

**目标：** PPT 渲染 + 快照导出，纯函数，不经 LLM。

| # | 任务 | 文件 | 行 | 内容 |
|---|------|------|-----|------|
| 5.1 | Assembly | `infrastructure/ppt_engine/assembly.py` | ~250 | `assemble_pptx(db, presentation_id, conv_id, user_id) → file_path`。流程: 读 slides → 每页 elements 按 z_order 排序 → 顺序调用 parser 添加 → 读 citations 查 knowledge_files → 增写 notes 引用 → 调 generator.generate_pptx() → snapshot |
| 5.2 | Exporter | `infrastructure/ppt_engine/exporter.py` | ~150 | `export_outline_snapshot(outline_id)`, `export_presentation_snapshot(pres_id)`。读 DB → 组装 JSON → 写 snapshots 表。Master 退出时调用 |

---

### Phase 6: API 层（2 文件，总计 ~250行）

**目标：** Chat 统一入口 + reexport/export 端点。

| # | 任务 | 文件 | 行 | 内容 |
|---|------|------|-----|------|
| 6.1 | Chat API（Master 入口） | `api/chat.py` | ~180 | `POST /api/chat` — 接收 `{message, conversation_id, web_search_enabled}`，调用 `run_master_agent()`，SSE 流式返回。替代当前 coordinator 路由。Tool messages 持久化到 messages 表（content_type="tool_call"/"tool_result"） |
| 6.2 | Reexport/Export API | `api/export.py` | ~70 | `POST /api/presentations/{id}/reexport` → `assemble_pptx()`。`GET /api/outlines/{id}/export?format=md&version=N` → `export_outline_snapshot()` |

---

### Phase 7: 全局索引重排（1 文件，~120行）

**目标：** 并行 outline_section 完成后统一分配全局 slide_index。

| # | 任务 | 文件 | 行 | 内容 |
|---|------|------|-----|------|
| 7.1 | Slide reindexer | `agent/tools/slide_reindexer.py` | ~120 | `reindex_slides(outline_id)` — 读取所有 sections → 按 section_index 排序 → title_slide=1 → 逐 section 逐 slide 分配全局 index → ending_slide=最大。在所有 outline_section 并行调用完成后由 Master 触发 |

---

### Phase 8: 清理（删除 ~15 文件）

| # | 删除文件 | 原因 |
|---|---------|------|
| 8.1 | `agent/coordinator.py` | → `agent/master.py` |
| 8.2 | `agent/outline/graph.py` | 不再需要 Graph 编排 |
| 8.3 | `agent/outline/middleware.py` | → `agent/common/token_middleware.py` |
| 8.4 | `agent/ppt/graph.py` | 不再需要 Graph 编排 |
| 8.5 | `agent/ppt/dispatcher.py` | → `agent/tools/slides_content.py` |
| 8.6 | `agent/ppt/phase1_style.py` | → `agent/tools/ppt_style.py` |
| 8.7 | `agent/ppt/phase2_super_freedom/agent.py` | → `agent/tools/slide_agent.py` |
| 8.8 | `agent/ppt/phase2_super_freedom/prompts.py` | → `agent/ppt/slide_prompts.py` |
| 8.9 | `agent/ppt/phase2_sub_agent/` (全 5 文件) | 已弃用 |
| 8.10 | `agent/ppt/phase2_freedom/` (全 2 文件) | 已弃用 |
| 8.11 | `agent/ppt/common/layout_resolver.py` | `select_layout` 内联到 structure.py |
| 8.12 | `agent/ppt/layout/definitions.py` | 对应 JSON 在 resources/layouts/ |
| 8.13 | `infrastructure/db/repository/template.py` | templates 表删除 |
| 8.14 | `infrastructure/db/repository/ppt.py` 中 `increment_slide_retry*` | retry 机制删除 |

---

### 最终文件清单（agent/ 目录，19 文件，总计 ~3500行）

```
agent/
├── common/
│   ├── langchain_adapter.py       (~90)  已有, 不改
│   ├── token_middleware.py        (~60)  新建 Phase1.2
│   └── model_builder.py           (~80)  新建 Phase1.3
├── master.py                      (~280) 新建 Phase2.4
├── master_prompts.py              (~120) 新建 Phase2.1
├── tools/
│   ├── perception.py              (~280) 新建 Phase2.2
│   ├── structure.py               (~180) 新建 Phase2.3
│   ├── outline_section.py         (~280) 新建 Phase3.1
│   ├── outline_evaluate.py        (~180) 新建 Phase3.2
│   ├── summarize_file.py          (~190) 新建 Phase3.3
│   ├── ppt_style.py               (~170) 新建 Phase4.4
│   ├── slide_agent.py             (~250) 新建 Phase4.1
│   ├── slides_content.py          (~250) 新建 Phase4.3
│   └── slide_reindexer.py         (~120) 新建 Phase7.1
├── outline/
│   ├── generator.py               (~250) 精简, 移除 graph 编排
│   ├── evaluator.py               (~190) 已有, 微调
│   ├── prompts.py                 (~100) 已有, 微调
│   └── state.py                   (~50)  已有, 微调
└── ppt/
    ├── common/
    │   ├── instruction_loader.py  (~80)  已有, 不改
    │   └── tools.py               (~200) 已有, 精简
    └── slide_prompts.py           (~180) 新建 Phase4.2
```

### 推荐实施顺序

```
Phase 0 (DB) ────────────────────────────── 先建表
    │
Phase 1 (Common) ─────────────────────────── 基础依赖
    │
Phase 2 (Master + 感知 + 结构) ──────────── 核心骨架 (可 review)
    │
Phase 3 (Outline 子Agent) ───────────────── 大纲能力
    │
Phase 4 (PPT 子Agent) ───────────────────── PPT 能力
    │
Phase 5 (Assembly + Exporter) ──────────── 渲染导出
    │
Phase 6 (API) ───────────────────────────── 对外接口
    │
Phase 7 (Reindexer) ─────────────────────── 收尾
    │
Phase 8 (清理) ──────────────────────────── 删旧文件
```
