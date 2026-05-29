# PPTGenius 数据库设计

> MySQL + asyncmy，SQLAlchemy async engine
> 日期：2026-06-04

---

## 一、ER 图

```
┌──────────┐
│  users   │
│──────────│
│ PK id    │
│   name   │
│   password│
│   other  │
└────┬─────┘
     │
┌────▼────────────┐         ┌─────────────────┐
│  conversations  │ 1     N │    messages     │
│─────────────────│─────────│─────────────────│
│ PK id           │         │ PK id           │
│ FK user_id      │         │ FK conversation │
│    title        │         │    idx          │
│    status       │         │    role         │
│    workspace    │         │    content      │
│ estimated_cost │         │ estimated_cost  │
└────────┬────────┘         └─────────────────┘
         │
         │ 1:N
         │
┌────────▼────────┐         ┌─────────────────────┐
│    outlines     │ 1     N │  outline_slides     │
│─────────────────│─────────│─────────────────────│
│ PK id           │         │ PK id               │
│ FK conversation │         │ FK outline_id       │
│ FK user_id      │         │    slide_index      │
│    title        │         │ UNIQUE(outline_id,  │
│    status       │         │        slide_index) │
│    eval_score   │         │    title            │
│    version      │         │    content_json     │
└────────┬────────┘         │    layout_type      │
         │                  │    has_image        │
         │ 1:N              │    has_chart        │
         │                  │    notes            │
         │                  │    created_at       │
         │                  └─────────────────────┘
└────────┬────────┘
         │
         │ 1:N
         │
┌──────────────────┐       ┌──────────────────────┐
│   presentations  │       │    color_schemes     │
│──────────────────│       │──────────────────────│
│ PK id            │   ┌───│ PK id                │
│ FK conversation  │   │   │    name (unique)     │
│ FK outline       │   │   │    label             │
│ FK user          │   │   │    colors_json       │
│ FK template ─────│───┘   │    chart_colors_json │
│ FK color_scheme ─│───────│    fonts_json        │
│    file_path     │       └──────────────────────┘
│    status        │
└────────┬─────────┘       ┌──────────────────────┐
         │                 │      templates       │
         │ 1:N             │──────────────────────│
         │                 │ PK id                │
┌────────▼──────────┐      │    name (unique)     │
│presentation_slides│      │    label             │
│──────────────────│      │    category          │
│ PK id            │      │    layouts_json      │
│ FK presentation  │      └──────────────────────┘
│ FK outline_slide │
│ FK template ─────│──┐
│ FK color_scheme ─│──┤
│    slide_index   │  │
│    layout_name   │  │
│    agent_outputs │  │
│    chart_data    │  │
│    table_data    │  │
│    image_paths   │  │
│    status        │  │
│    error_message │  │
│    retry_count   │  │
└──────────────────┘  │
                       │
┌─────────────────┐    │
│ knowledge_files │    │
│─────────────────│    │
│ PK id           │    │
│ FK user_id      │    │
│    filename     │    │
│    file_path    │    │
│    file_type    │    │
│    file_size    │    │
│    chunk_count  │    │
│    source_type  │    │
│    status       │    │
└────────┬────────┘    │
         │ 1:N         │
┌────────▼────────┐    │
│ knowledge_chunks│    │
│─────────────────│    │
│ PK id           │    │
│ FK file_id (CASCADE)│
│    chunk_index  │    │
│    chunk_text   │    │
│    token_count  │    │
└─────────────────┘    │
                       └── color_schemes (同上 FK)
```

---

##### presentation_snapshots

PPT 快照表，每次生成/修改后存入完整的 outline + presentation JSON。

| 列名 | 类型 | 说明 |
|------|------|------|
| `id` | INT PK | |
| `presentation_id` | FK CASCADE | |
| `user_id` | FK | |
| `conversation_id` | FK | |
| `outline_json` | JSON | 完整的 outline 快照 |
| `presentation_json` | JSON | 完整的 presentation (slides) 快照 |
| `version` | INT | 快照版本号，同 presentation 内自增 |
| `created_at` | DATETIME | |

---

## 二、关键设计决策

| 决策 | 说明 |
|------|------|
| **软删除** | conversations、outlines、presentations 的 `status` 可设为 `deleted`，查询时自动过滤 |
| **messages.idx** | 替代 id 做排序，`trim_messages(before_idx)` 删除旧消息控制上下文窗口 |
| **outlines 移除 eval_feedback / user_feedback** | 反馈由 messages 表记录，不在 outline 表冗余 |
| **knowledge_chunks ON DELETE CASCADE** | 删除 knowledge_file 时自动删除其所有 chunks |
| **conversation.workspace_path 由 id 自动生成** | `./data/workspace/{id}`，创建时不传入 |
| **message 创建自动累加 cost** | `estimated_cost` 为本次 LLM 调用的 CNY 费用，自动累加到 conversation.estimated_cost |
| **presentation_slides.agent_outputs** | 每个 sub-agent 独立写入 JSON checkpoint，supervisor 重试时只重试失败的 agent |
| **templates / color_schemes** | 独立表存储模板和配色方案，layout_agent 选择已有方案或调用 create 新建 |
| **users.password + users.other** | 预留多用户认证和扩展字段 |
| **presentation_snapshots** | PPT 快照，存储每次生成/修改后的完整 outline + presentation JSON，version 自增 |
| **web_resources 表已删除** | Web 内容统一走 KnowledgeService + knowledge_files |
| **图片不入 BM25** | 图片上传后存入 `workspace/{id}/input/`，创建 image message，不进入 knowledge_files |
| **文件上传自动预览** | 文档上传后取前1000字符创建 file message (role="file")，LLM 即可直接阅读 |
| **message role 扩展** | 新增 file / image 两种角色，content_type 字段区分消息类型 |
| **outline_slides 唯一约束** | (outline_id, slide_index) 联合唯一 |

---

## 三、新增表：templates & color_schemes

### templates

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INT | PK, AUTO_INCREMENT | |
| `name` | VARCHAR(50) | UNIQUE, NOT NULL | 模板标识 |
| `label` | VARCHAR(100) | NOT NULL | 显示名 |
| `category` | VARCHAR(50) | | corporate / tech / education / creative / minimal |
| `description` | VARCHAR(500) | | |
| `slide_width` | FLOAT | DEFAULT 13.333 | 16:9 |
| `slide_height` | FLOAT | DEFAULT 7.5 | |
| `layouts_json` | JSON | NOT NULL | 布局定义 [{name, label, placeholders}] |
| `is_active` | BOOLEAN | DEFAULT TRUE | |
| `created_at` | DATETIME | DEFAULT CURRENT_TIMESTAMP | |
| `updated_at` | DATETIME | ON UPDATE CURRENT_TIMESTAMP | |

### color_schemes

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INT | PK, AUTO_INCREMENT | |
| `name` | VARCHAR(50) | UNIQUE, NOT NULL | 方案标识 |
| `label` | VARCHAR(100) | NOT NULL | 显示名 |
| `colors_json` | JSON | NOT NULL | {primary, accent, text, bg, ...} |
| `chart_colors_json` | JSON | NOT NULL | 图表配色序列 |
| `fonts_json` | JSON | NOT NULL | {title, subtitle, body, caption} |
| `style_density` | VARCHAR(16) | DEFAULT 'moderate' | minimal / moderate / elaborate |
| `decoration_json` | JSON | | 装饰开关 {title_accent_bar, section_divider_line, corner_bracket, ...} |
| `is_active` | BOOLEAN | DEFAULT TRUE | |
| `created_at` | DATETIME | DEFAULT CURRENT_TIMESTAMP | |
| `updated_at` | DATETIME | ON UPDATE CURRENT_TIMESTAMP | |

---

## 四、知识库表

### knowledge_files

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INT | PK, AUTO_INCREMENT | |
| `user_id` | INT | FK → users.id, NOT NULL | |
| `filename` | VARCHAR(256) | NOT NULL | 原始文件名 |
| `file_path` | VARCHAR(512) | NOT NULL | 实际存储路径 |
| `file_type` | VARCHAR(16) | NOT NULL | pdf / docx / xlsx / csv / txt / md / pptx |
| `file_size` | INT | | 文件大小 (bytes) |
| `chunk_count` | INT | DEFAULT 0 | |
| `source_type` | VARCHAR(16) | DEFAULT 'upload' | upload / web |
| `status` | VARCHAR(32) | DEFAULT 'indexed' | indexed / deleted |
| `created_at` | DATETIME | DEFAULT CURRENT_TIMESTAMP | |

### knowledge_chunks

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INT | PK, AUTO_INCREMENT | |
| `file_id` | INT | FK → knowledge_files.id, ON DELETE CASCADE | |
| `chunk_index` | INT | NOT NULL | 文件内 chunk 序号 |
| `chunk_text` | TEXT | NOT NULL | chunk 文本内容 |
| `token_count` | INT | | 估算 token 数 |
| `created_at` | DATETIME | DEFAULT CURRENT_TIMESTAMP | |

---

## 五、presentations / presentation_slides 变更

### presentations 新增字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `template_id` | FK → templates.id | 模板引用 |
| `color_scheme_id` | FK → color_schemes.id | 配色引用 |

### presentation_slides 表结构

| 列名 | 类型 | 说明 |
|------|------|------|
| `id` | INT PK | |
| `presentation_id` | FK CASCADE | |
| `outline_slide_id` | FK SET NULL | 对应大纲页 |
| `slide_index` | INT | 页码 |
| `template_id` | FK SET NULL | 页级模板覆盖 |
| `color_scheme_id` | FK SET NULL | 页级配色覆盖 |
| `layout_name` | VARCHAR(50) | layout 名 |
| `agent_outputs` | JSON | {"text": [...], "chart": {...}, "table": {...}, "image": {...}} |
| `chart_data` | JSON | 图表纯数据 |
| `table_data` | JSON | 表格纯数据 |
| `image_paths` | JSON | 图片路径列表 |
| `status` | VARCHAR(20) | pending / text_generating / chart_generating / completed / failed |
| `error_message` | TEXT | |
| `retry_count` | INT DEFAULT 0 | |

---

## 六、outline_slides 补充 & messages 角色

### outline_slides 约束

| 约束 | 说明 |
|------|------|
| `UNIQUE KEY uk_outline_slide (outline_id, slide_index)` | 同一 outline 内 slide_index 唯一 |

### messages 角色 (role)

| role | 说明 | content_type |
|------|------|-------------|
| `user` | 用户消息 | text |
| `assistant` | AI 回复 | text |
| `file` | 文件上传后自动创建，含前1000字符预览 | file |
| `image` | 图片上传后自动创建，含路径、类型、大小 | image |

---

## 七、索引

```sql
CREATE INDEX idx_conv_user ON conversations(user_id);
CREATE INDEX idx_msg_conv_idx ON messages(conversation_id, idx);
CREATE INDEX idx_out_conv ON outlines(conversation_id, version DESC);
CREATE INDEX idx_out_user ON outlines(user_id);
CREATE INDEX idx_pres_conv ON presentations(conversation_id);
CREATE INDEX idx_pres_user ON presentations(user_id);
CREATE INDEX idx_pslide_pres ON presentation_slides(presentation_id, slide_index);
CREATE INDEX idx_pslide_status ON presentation_slides(status);
CREATE INDEX idx_pslide_outline ON presentation_slides(outline_slide_id);
CREATE INDEX idx_template_cat ON templates(category);
CREATE INDEX idx_colorscheme_name ON color_schemes(name);
CREATE INDEX idx_snap_pres ON presentation_snapshots(presentation_id, version DESC);
CREATE INDEX idx_know_user ON knowledge_files(user_id);
CREATE INDEX idx_kchunk_file ON knowledge_chunks(file_id, chunk_index);
```
