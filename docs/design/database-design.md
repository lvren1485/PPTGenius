# PPTGenius 数据库设计

> MySQL + asyncmy，SQLAlchemy async engine
> 日期：2026-06-03

---

## 一、ER 图

```
┌──────────┐
│  users   │
│──────────│
│ PK id    │
└────┬─────┘
     │
┌────▼────────────┐         ┌─────────────────┐
│  conversations  │ 1     N │    messages     │
│─────────────────│─────────│─────────────────│
│ PK id           │         │ PK id           │
│ FK user_id      │         │ FK conversation │
│    title        │         │    idx          │ ← 新增：排序索引
│    status       │         │    role         │
│    workspace    │         │    content      │
│    total_tokens │         │    token_count  │
└────────┬────────┘         └─────────────────┘
         │
         │ 1:N
         │
┌────────▼────────┐         ┌─────────────────┐
│    outlines     │ 1     N │  outline_slides │
│─────────────────│─────────│─────────────────│
│ PK id           │         │ PK id           │
│ FK conversation │         │ FK outline_id   │
│ FK user_id      │         │    slide_index  │
│    title        │         │    title        │
│    status       │         │    content_json │
│    eval_score   │         │    layout_type  │
│    version      │         └─────────────────┘
└────────┬────────┘
         │
         │ 1:N
         │
┌────────▼────────┐         ┌──────────────────┐
│  presentations  │ 1     N │ presentation_slides│
│─────────────────│─────────│───────────────────│
│ PK id           │         │ PK id             │
│ FK conversation │         │ FK presentation   │
│ FK outline      │         │    slide_index    │
│ FK user_id      │         │    layout_type    │
│    file_path    │         │    color_scheme   │
│    status       │         └───────────────────┘
└─────────────────┘

┌─────────────────┐         ┌──────────────────┐
│ knowledge_files │ 1     N │ knowledge_chunks │
│─────────────────│─────────│──────────────────│
│ PK id           │         │ PK id            │
│ FK user_id      │         │ FK file_id       │
│    filename     │         │    chunk_index   │
│    file_type    │         │    chunk_text    │
│    status       │         └──────────────────┘
└─────────────────┘         ON DELETE CASCADE

┌──────────────────┐
│  web_resources   │
│──────────────────│
│ PK id            │
│ FK user_id       │
│    url           │
│    content_text  │
│    source_domain │
└──────────────────┘
```

---

## 二、关键设计决策

| 决策 | 说明 |
|------|------|
| **软删除** | conversations、outlines、presentations 的 `status` 可设为 `deleted`，查询时自动过滤。避免级联删除带来的外键问题。 |
| **messages 的 idx 字段** | 替代 id 做排序，`trim_messages(before_idx)` 删除 idx 之前的旧消息，控制上下文窗口。 |
| **outlines 移除了 eval_feedback / user_feedback** | 反馈通过 messages 表的多轮对话记录，不在 outline 表冗余存储。 |
| **knowledge_files 移除了 content_hash** | 无需 hash 去重，文件和 web resource 不同源不同策略。 |
| **knowledge_chunks ON DELETE CASCADE** | 删除 knowledge_file 时自动删除其所有 chunks，避免检索到已删除文件的残留数据。 |
| **conversation.workspace_path 由 id 自动生成** | `./data/workspace/{conversation_id}`，创建时不传入。 |
| **message 创建时自动累加 token** | `create_message` 的 `token_count` 参数含义为"距上次 AIMessage 后本轮总消耗"，自动累加到 conversation.total_tokens。 |
| **presentation 表暂定** | 待调研 python-pptx 后确定最终结构。 |

---

## 三、索引

```sql
CREATE INDEX idx_conv_user ON conversations(user_id);
CREATE INDEX idx_msg_conv_idx ON messages(conversation_id, idx);
CREATE INDEX idx_out_conv ON outlines(conversation_id, version DESC);
CREATE INDEX idx_out_user ON outlines(user_id);
CREATE INDEX idx_pres_conv ON presentations(conversation_id);
CREATE INDEX idx_pres_user ON presentations(user_id);
CREATE INDEX idx_pslide_pres ON presentation_slides(presentation_id, slide_index);
CREATE INDEX idx_know_user ON knowledge_files(user_id);
CREATE INDEX idx_kchunk_file ON knowledge_chunks(file_id, chunk_index);
CREATE UNIQUE INDEX idx_web_url ON web_resources(url);
CREATE INDEX idx_web_user ON web_resources(user_id);
```
