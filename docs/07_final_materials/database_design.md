# PPTGenius Database Design

> 版本: 0.3.0 | 日期: 2026-06-17 | 基于 `infrastructure/db/models.py` 实际 ORM

---

## 目录

1. [表关系图](#1-表关系图)
2. [表定义](#2-表定义)
3. [版本号系统](#3-版本号系统)
4. [消息持久化](#4-消息持久化)
5. [Snapshot 机制](#5-snapshot-机制)
6. [Token 统计](#6-token-统计)

---

## 1. 表关系图

```
users (1) ─────┬── (N) conversations ───┬── (N) messages
                │                       │
                │                       ├── (N) outlines ──┬── (N) outline_sections
                │                       │                  │        │
                │                       │                  │        └── (N) outline_slides
                │                       │                  │
                │                       │                  └── (N) outline_snapshots
                │                       │
                │                       ├── (N) presentations ──┬── (N) presentation_slides
                │                       │                       │
                │                       │                       └── (N) presentation_snapshots
                │                       │
                │                       └── (N) knowledge_files ── (N) knowledge_chunks
                │
                └── styles (独立, 无 user FK)
```

**关键外键:**
- `conversations.current_outline_id` → `outlines.id` (当前活跃大纲)
- `outline_slides.section_id` → `outline_sections.id`
- `presentations.outline_id` → `outlines.id` (1:N)
- `presentation_slides.outline_slide_id` → `outline_slides.id`

---

## 2. 表定义

### users
| 列 | 类型 | 说明 |
|----|------|------|
| id | INT PK | 自增 |
| name | VARCHAR(64) | 用户名 |
| password | VARCHAR(256) | PBKDF2-SHA256 哈希 |
| other | JSON | 扩展字段 (web_search_enabled, rag_mode) |
| created_at | DATETIME | |

### conversations
| 列 | 类型 | 说明 |
|----|------|------|
| id | INT PK | 自增 |
| user_id | INT FK → users | |
| title | VARCHAR(256) | |
| status | VARCHAR(32) | active / archived / deleted |
| current_outline_id | INT FK → outlines (nullable) | 当前选中大纲 |
| workspace_path | VARCHAR(512) | |
| estimated_cost | FLOAT | 累计费用 (USD) |
| context_usage | FLOAT | 0.0~1.0, context window 使用率 |
| created_at / updated_at | DATETIME | |

### messages
| 列 | 类型 | 说明 |
|----|------|------|
| id | INT PK | 自增 |
| conversation_id | INT FK → conversations | |
| idx | INT | 消息序号 (前端排序) |
| role | VARCHAR(16) | user / assistant / tool_call / tool_result / document |
| content | TEXT | 消息内容 |
| content_type | VARCHAR(32) | text / tool_call / document / ... |
| estimated_cost | FLOAT | token 费用 (USD) |
| token_cost_json | JSON | `{input_tokens, output_tokens, total_tokens, ...}` |
| metadata_json | JSON | `{tool_name, args, ...}` |
| created_at | DATETIME | |

**content_type 值域**: `text`, `tool_call`, `tool_result`, `system`, `file`, `document`, `summary`, `conv_status`, `switch_outline`, `get_outline`, `get_slide`, `get_pres`, `get_kfiles`, `search_styles`, `create_outline`, `write_outline`, `mod_outline`, `rearr_pres`, `gen_content`, `mod_section`, `evaluate`, `explore`, `ppt_style`, `slides_content`, `mod_slides`

### outlines
| 列 | 类型 | 说明 |
|----|------|------|
| id | INT PK | 自增 |
| user_id / conversation_id | FK | |
| title | VARCHAR(256) | |
| status | VARCHAR(32) | draft / completed / confirmed / deleted |
| eval_score | FLOAT | 0-10 评测分数 |
| eval_detail | JSON | 评测详情 (suggestions 数组) |
| version | INT | 单调递增, 默认 0, 每次修改 +1 |
| explore_result_json | JSON | Explore 完整输出 (section 划分+引用) |
| slide_count | INT | |
| created_at / updated_at | DATETIME | |

### outline_sections
| 列 | 类型 | 说明 |
|----|------|------|
| id | INT PK | 自增 |
| outline_id | INT FK → outlines CASCADE | |
| section_index | INT | 从 1 开始 |
| title | VARCHAR(256) | |
| description | TEXT | |
| slide_count | INT | |
| citations | JSON | `[{knowledge_file_id, chunk_id, ...}]` |
| created_at | DATETIME | |

### outline_slides
| 列 | 类型 | 说明 |
|----|------|------|
| id | INT PK | 自增 |
| outline_id | INT FK → outlines | |
| section_id | INT FK → outline_sections (nullable) | |
| slide_index | INT | 全局序号, 从 1 开始 |
| title | VARCHAR(256) | |
| content_json | JSON | `{main_points, detailed_content, recommended_ppt_format, ...}` |
| layout_type | VARCHAR(32) | title / content / thanks / two_column / ... |
| has_image / has_chart | BOOL | |
| notes | TEXT | |
| citations | JSON | `[{chunk_id, knowledge_file_id, reason}]` |
| status | VARCHAR(32) | pending / completed / merge / split / fill / new / modify |
| created_at | DATETIME | |

### outline_snapshots
| 列 | 类型 | 说明 |
|----|------|------|
| id | INT PK | 自增 |
| outline_id | INT FK → outlines CASCADE | |
| user_id / conversation_id | FK | |
| version | INT | 对应 outlines.version |
| outline_json | JSON | 完整大纲快照 (标题+sections+slides) |
| created_at | DATETIME | |

### presentations
| 列 | 类型 | 说明 |
|----|------|------|
| id | INT PK | 自增 |
| user_id / conversation_id | FK | |
| outline_id | INT FK → outlines (nullable) | |
| style_id | INT FK → styles (nullable) | |
| slide_count | INT | |
| version | INT | 同一 outline_version 下的 PPT 迭代次数 |
| outline_version | INT | 生成时对应的大纲版本 |
| status | VARCHAR(32) | pending / completed |
| created_at / updated_at | DATETIME | |

### presentation_slides
| 列 | 类型 | 说明 |
|----|------|------|
| id | INT PK | 自增 |
| presentation_id | INT FK → presentations CASCADE | |
| outline_slide_id | INT FK → outline_slides (nullable) | |
| slide_index | INT | |
| style_id | INT FK → styles (nullable) | |
| status | VARCHAR(32) | pending / completed |
| agent_outputs | JSON | `{elements: [...], notes: "...", background: {...}}` |
| created_at / updated_at | DATETIME | |

### styles
| 列 | 类型 | 说明 |
|----|------|------|
| id | INT PK | 自增 |
| name | VARCHAR(50) UNIQUE | |
| label | VARCHAR(100) | |
| colors_json | JSON | `{primary, accent, background, text, ...}` |
| chart_colors_json | JSON | |
| fonts_json | JSON | `{title, body, ...}` |
| style_density | VARCHAR(16) | sparse / moderate / dense |
| decoration_json | JSON | |
| background_json | JSON | |
| is_active | BOOL | |
| created_at / updated_at | DATETIME | |

### knowledge_files
| 列 | 类型 | 说明 |
|----|------|------|
| id | INT PK | 自增 |
| user_id | INT FK → users | |
| conversation_id | INT FK → conversations | |
| filename | VARCHAR(256) | |
| file_type | VARCHAR(32) | pdf / docx / txt / csv / xlsx |
| file_size | INT | |
| source_type | VARCHAR(32) | upload / web |
| web_url | VARCHAR(2048) | fetch_web 回写源 URL |
| chunks_count | INT | |
| summary_json | JSON | LLM 摘要 (纯文本) |
| status | VARCHAR(32) | pending / indexed / summarised |
| created_at | DATETIME | |

### knowledge_chunks
| 列 | 类型 | 说明 |
|----|------|------|
| id | INT PK | 自增 |
| file_id | INT FK → knowledge_files CASCADE | |
| chunk_index | INT | |
| chunk_text | TEXT | |
| token_count | INT | |

---

## 3. 版本号系统

- **outlines.version** — 单调递增 int (替代旧三段式 major/minor/patch)。`write_outline_structure`、`modify_outline_structure`、`outline_section` 完成时自增。
- **presentations.version** — 同一 outline_version 下的 PPT 迭代次数
- **presentations.outline_version** — 生成时对应的大纲版本。`outline_version < outline.version` 表示 PPT 过期需重新生成。
- **outline_snapshots.version** — 直接记录 outlines.version
- **presentation_snapshots.version** — 记录 `{outline_version, presentation_version}` 组合

```
outline id=1, version=1
  ├─ presentation version=1 (outline_version=1)  ← 首次生成
  └─ presentation version=2 (outline_version=1)  ← 微调后重生成

outline id=1, version=2   ← 大纲修改
  └─ presentation version=1 (outline_version=2)  ← 重新计数
```

---

## 4. 消息持久化

`messages` 表持久化工具调用:
- `tool_call` — Master 调用工具时写入, metadata_json 含 `{tool_name, args, tool_call_id}`
- `tool_result` — 工具返回时写入, metadata_json 含 `{tool_name, tool_call_id, result_len}`

`PersistToolMiddleware` 在每次工具调用时逐步写入 (不等待 Agent 结束)。

前端通过 `visibleMessages` 计算属性将 `tool_call`/`tool_result` 分组为 `ToolBlock` 渲染。

---

## 5. Snapshot 机制

Master 每轮处理完毕后检查变更:
- outlines 有变更 → `export_outline_snapshot(current_outline_id)` → 写 `outline_snapshots`
- presentations 有变更 → `export_presentation_snapshot(current_pres_id)` → 写 `presentation_snapshots`

导出基于 snapshot (不可变历史)，而非直接读当前状态。

---

## 6. Token 统计

- `agent_id` 不存入任何表，仅作为内存中 `TokenCounter` 的 key
- `token_cost_json` 仅存在于 `messages` 表
- 双层计数: `TokenCounter._conv_counters` (conversation_id) + `TokenCounter._agent_counters` (agent_id)
- 子 Agent 工具返回时汇总并发 agent 的 token cost → 写入对应 tool_result 消息
