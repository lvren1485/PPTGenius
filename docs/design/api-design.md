# PPTGenius API 设计

> RESTful API，FastAPI 实现，SSE 流式响应
> 日期：2026-06-03 · 最后更新：Agent supervisor 统一入口 + conversation 作用域

---

## 一、通用约定

### Base URL

```
http://localhost:8000/api
```

### 通用响应

```json
{ "code": 0, "message": "ok", "data": { ... } }
```

### 错误码

| 范围 | 类型 |
|------|------|
| 40001-40099 | 资源不存在 |
| 40100-40199 | 参数校验 |
| 40200-40299 | Agent 执行错误 |
| 40300-40399 | 文件处理 |
| 40400-40499 | PPT 生成 |
| 50001-50099 | 系统内部 |

### 认证

单人网站暂不设认证。各接口暂用固定 `user_id=1`。后续如需认证，加 `Authorization: Bearer <token>` Header，从 token 解析 user_id。

### 对话模型

**Agent supervisor 统一决策。** 前端只通过 `POST /api/chat/send` 发送用户消息，Agent 内部判断当前阶段（生成大纲 / 修改大纲 / 生成 PPT / 修改 PPT / 重新开始）。不为 outline/ppt 提供独立的 POST/PUT 端点 — 全部由 Agent 驱动。

```
用户消息 → POST /api/chat/send → Agent supervisor
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              生成大纲         修改大纲          生成PPT
              评估+修改       应用反馈          supervisor
              确认等待        继续评估          sub-agents
                    │               │               │
                    └───────────────┴───────────────┘
                                    │
                                    ▼
                            SSE 流式返回
```

---

## 二、端点总览

```
# ── 对话（唯一写入口）──
POST   /api/chat/send                  发送消息（SSE 流式）

# ── 会话 ──
POST   /api/conversations              创建会话
GET    /api/conversations              会话列表
GET    /api/conversations/{id}         会话详情（含消息 + outline/ppt 摘要）
DELETE /api/conversations/{id}         删除会话

# ── 大纲（只读）──
GET    /api/outlines                   大纲列表
GET    /api/outline/{id}               大纲详情（含 slides）
GET    /api/outline/{id}/slides        大纲 slides 列表

# ── PPT（只读）──
GET    /api/presentations              PPT 列表
GET    /api/ppt/{id}                   PPT 详情
GET    /api/ppt/{id}/slides            PPT slide 详情（含 agent_outputs、status）
GET    /api/ppt/{id}/download          下载 .pptx

# ── 快照（只读）──
GET    /api/ppt/{id}/snapshots         版本快照列表
GET    /api/snapshots/{id}             快照详情

# ── 费用统计 ──
GET    /api/cost/summary               费用汇总
GET    /api/cost/by-date               按日期统计
GET    /api/cost/by-conversation       按会话统计

# ── 知识库（文件管理；BM25 检索由 Agent 内部调用）──
POST   /api/knowledge/upload           上传文件（存入 conversation workspace）
GET    /api/knowledge/files            文件列表
DELETE /api/knowledge/files/{id}       删除文件

# ── 工作空间 & 系统 ──
GET    /api/workspace/status           工作空间状态
GET    /api/config                     获取配置
GET    /api/health                     健康检查
```

---

## 三、详细接口

### 3.1 对话 — POST /api/chat/send

**唯一写入口。** 所有用户消息都通过此端点发送，Agent supervisor 自行判断当前阶段并驱动流程。

```
Request:
{
  "user_id": 1,
  "conversation_id": 1,
  "message": "我想做一个关于Python数据分析的PPT"
  // 早期阶段: "加一个实战案例"  → Agent 判断：修改大纲
  // 确认阶段: "可以，生成PPT"   → Agent 判断：开始生成 PPT
  // 修改阶段: "第3页太挤了"     → Agent 判断：修改 PPT
}
```

**Response: text/event-stream**

```
# ── RAG 检索阶段 ──
event: phase
data: {"phase": "rag", "message": "检索知识库..."}

event: knowledge
data: {"sources": [{"filename": "report.pdf", "chunk_id": 5, "score": 12.3}]}

# ── 大纲阶段 ──
event: phase
data: {"phase": "outline", "message": "开始生成大纲..."}

event: progress
data: {"step": "generating", "detail": "正在生成第1版大纲...", "pct": 10}

event: progress
data: {"step": "evaluating", "detail": "评估评分 0.72，正在修改...", "pct": 30}

event: outline
data: {"outline_id": 1, "title": "Python数据分析入门",
       "slides": [{"slide_index": 0, "title": "...", "layout_type": "title", ...}],
       "eval_score": 0.85}

event: phase
data: {"phase": "waiting_user", "message": "请确认大纲，或提出修改意见"}

# ── 用户继续发送消息后 ──

event: phase
data: {"phase": "outline", "message": "根据反馈修改大纲..."}

event: outline
data: {"outline_id": 1, "title": "...", "slides": [...], "eval_score": 0.90}

event: phase
data: {"phase": "waiting_user", "message": "大纲已更新，确认或继续修改"}

# ── 用户确认后进入 PPT 阶段 ──

event: phase
data: {"phase": "ppt", "message": "开始生成PPT..."}

event: progress
data: {"step": "generating_slides", "detail": "3/12...", "pct": 60}

event: ppt_ready
data: {"presentation_id": 1, "file_path": "...", "slide_count": 12,
       "download_url": "/api/ppt/1/download"}

event: done
data: {"estimated_cost": 0.0062, "elapsed_seconds": 45.2}

# ── 错误 ──
event: error
data: {"code": 40201, "message": "LLM timeout", "retryable": true}
```

**为什么选 SSE 而非 WebSocket：**
- 对话是 request-response 模式（用户发一条 → Agent 流式返回），天然匹配 HTTP + SSE
- WebSocket 需要管理连接生命周期、心跳、重连，对单人应用过度
- SSE 通过标准 HTTP，代理/CDN 兼容性好
- 如需后续切换：将 `POST /api/chat/send` 改为 `WS /api/chat/{conversation_id}` 即可，不影响 Agent 层

---

### 3.2 会话

#### POST /api/conversations

```
Request:  { "user_id": 1, "title": "关于AI的PPT" }

Response 201:
{
  "code": 0,
  "data": {
    "id": 1, "user_id": 1, "title": "关于AI的PPT",
    "status": "active", "current_phase": "chat",
    "workspace_path": "data/workspace/1/", "created_at": "..."
  }
}
```

#### GET /api/conversations

```
Query: ?user_id=1&status=active&page=1&page_size=20

Response 200:
{
  "code": 0,
  "data": {
    "items": [{
      "id": 1, "user_id": 1, "title": "关于AI的PPT", "status": "active",
      "current_phase": "outline", "message_count": 5,
      "estimated_cost": 0.032, "created_at": "...", "updated_at": "..."
    }],
    "total": 1, "page": 1, "page_size": 20
  }
}
```

#### GET /api/conversations/{id}

返回会话详情 + 消息列表 + 关联的 outline 和 presentation 摘要。

```
Response 200:
{
  "code": 0,
  "data": {
    "id": 1, "user_id": 1, "title": "关于AI的PPT",
    "status": "active", "current_phase": "ppt",
    "workspace_path": "data/workspace/1/",
    "estimated_cost": 0.045,
    "created_at": "...", "updated_at": "...",
    "messages": [
      {"id": 1, "idx": 1, "role": "user", "content": "做一个Python PPT",
       "content_type": "text", "estimated_cost": 0, "created_at": "..."},
      {"id": 2, "idx": 2, "role": "assistant", "content": "好的，我先生成大纲...",
       "content_type": "text", "estimated_cost": 0.002, "created_at": "..."}
    ],
    "outlines": [
      {"id": 1, "title": "Python数据分析入门", "status": "confirmed",
       "version": 2, "slide_count": 12, "eval_score": 0.85, "created_at": "..."}
    ],
    "presentations": [
      {"id": 1, "status": "completed", "slide_count": 12,
       "file_path": "data/workspace/1/output/xxx.pptx", "created_at": "..."}
    ]
  }
}
```

#### DELETE /api/conversations/{id}

软删除（status=deleted）。可选 `?hard=true` 硬删除连带 workspace 文件。

---

### 3.3 大纲（只读）

> Agent 负责生成/修改大纲。前端通过 `POST /api/chat/send` 发送用户反馈即可。
> 以下端点仅用于**查看**。

#### GET /api/outlines — 大纲列表

```
Query: ?user_id=1              按用户筛选（必填）
Query: ?conversation_id=1      按会话筛选（可选）
Query: ?page=1&page_size=20

Response 200:
{
  "code": 0,
  "data": {
    "items": [
      {"id": 1, "user_id": 1, "conversation_id": 1,
       "title": "Python数据分析入门", "status": "confirmed",
       "version": 2, "slide_count": 12, "eval_score": 0.85,
       "created_at": "...", "updated_at": "..."}
    ],
    "total": 1, "page": 1, "page_size": 20
  }
}
```

#### GET /api/outline/{id} — 详情（含 slides）

```
Response 200:
{
  "code": 0,
  "data": {
    "id": 1,
    "user_id": 1,
    "conversation_id": 1,
    "title": "Python数据分析入门",
    "status": "confirmed",
    "eval_score": 0.85,
    "version": 2,
    "slide_count": 12,
    "created_at": "...",
    "updated_at": "...",
    "slides": [
      {"id": 10, "slide_index": 0, "title": "课程简介",
       "layout_type": "title",
       "content_json": {"subtitle": "从零开始掌握数据分析"},
       "has_image": false, "has_chart": false, "notes": "讲师自我介绍"},
      {"id": 11, "slide_index": 1, "title": "环境搭建",
       "layout_type": "content",
       "content_json": {"bullets": ["安装Python", "pip install pandas", "Jupyter配置"]},
       "has_image": false, "has_chart": false, "notes": null}
    ]
  }
}
```

#### GET /api/outline/{id}/slides — 仅 slides 列表

返回 `slides` 数组，结构同上。

---

### 3.4 PPT（只读）

> Agent 负责生成/修改 PPT。前端通过 `POST /api/chat/send` 发送用户反馈即可。
> 以下端点仅用于**查看**和**下载**。

#### GET /api/presentations — PPT 列表

```
Query: ?user_id=1              按用户筛选（必填）
Query: ?conversation_id=1      按会话筛选（可选）
Query: ?page=1&page_size=20

Response 200:
{
  "code": 0,
  "data": {
    "items": [
      {"id": 1, "user_id": 1, "conversation_id": 1, "outline_id": 1,
       "status": "completed", "slide_count": 12,
       "file_path": "data/workspace/1/output/xxx.pptx",
       "file_size": 46780, "created_at": "...", "updated_at": "..."}
    ],
    "total": 1, "page": 1, "page_size": 20
  }
}
```

#### GET /api/ppt/{id} — 详情

```
Response 200:
{
  "code": 0,
  "data": {
    "id": 1, "user_id": 1,
    "conversation_id": 1, "outline_id": 1,
    "template_id": 1, "color_scheme_id": 2,
    "file_path": "data/workspace/1/output/xxx.pptx",
    "file_size": 46780, "slide_count": 12,
    "status": "completed", "error_msg": null,
    "created_at": "...", "updated_at": "..."
  }
}
```

#### GET /api/ppt/{id}/slides — 所有 slide 详情

查看每页 slide 的 agent 产出、状态、重试信息。

```
Response 200:
{
  "code": 0,
  "data": {
    "presentation_id": 1,
    "slides": [
      {"id": 100, "slide_index": 0, "layout_name": "title_slide",
       "outline_slide_id": 10, "template_id": 1, "color_scheme_id": 2,
       "status": "completed", "retry_count": 0,
       "agent_outputs": {"text": {"title": "Python数据分析"}, "image": {...}},
       "chart_data": null, "table_data": null, "image_paths": {...},
       "error_message": null},
      {"id": 101, "slide_index": 1, "layout_name": "content_chart",
       "status": "failed", "retry_count": 3,
       "agent_outputs": {"text": {"title": "数据趋势"}},
       "chart_data": {"type": "line", "data": [...]},
       "error_message": "chart_agent timeout after 3 retries"}
    ]
  }
}
```

#### GET /api/ppt/{id}/download — 下载

```
Response 200: application/vnd.openxmlformats-officedocument.presentationml.presentation
Content-Disposition: attachment; filename="Python数据分析入门.pptx"
```

---

### 3.5 快照（只读）

PPT 每次成功生成/修改后保存完整快照，用于版本回溯。

#### GET /api/ppt/{id}/snapshots — 快照列表

```
Response 200:
{
  "code": 0,
  "data": {
    "presentation_id": 1,
    "snapshots": [
      {"id": 5, "version": 3, "created_at": "..."},
      {"id": 3, "version": 2, "created_at": "..."},
      {"id": 1, "version": 1, "created_at": "..."}
    ]
  }
}
```

#### GET /api/snapshots/{id} — 快照详情

```
Response 200:
{
  "code": 0,
  "data": {
    "id": 5,
    "presentation_id": 1,
    "user_id": 1,
    "conversation_id": 1,
    "version": 3,
    "outline_json": {
      "title": "Python数据分析入门",
      "slides": [{"title": "...", "content_json": {...}}, ...]
    },
    "presentation_json": {
      "slide_count": 12,
      "slides": [{"layout_name": "title_slide", "agent_outputs": {...}}, ...]
    },
    "created_at": "..."
  }
}
```

---

### 3.6 费用统计

所有端点按 `user_id` 筛选。

#### GET /api/cost/summary — 费用汇总

```
Query: ?user_id=1&days=30

Response 200:
{
  "code": 0,
  "data": {
    "user_id": 1,
    "total_cost": 1.256,
    "total_conversations": 15,
    "total_messages": 230,
    "avg_cost_per_conversation": 0.084,
    "avg_cost_per_day": 0.042,
    "days": 30
  }
}
```

#### GET /api/cost/by-date — 按日期统计

```
Query: ?user_id=1&days=30&page=1&page_size=30

Response 200:
{
  "code": 0,
  "data": {
    "items": [
      {"date": "2026-06-03", "cost": 0.152, "conversations": 3, "messages": 25},
      {"date": "2026-06-02", "cost": 0.083, "conversations": 2, "messages": 18}
    ],
    "total": 30, "page": 1, "page_size": 30
  }
}
```

#### GET /api/cost/by-conversation — 按会话统计

```
Query: ?user_id=1&days=30&page=1&page_size=20

Response 200:
{
  "code": 0,
  "data": {
    "items": [
      {"conversation_id": 1, "title": "关于AI的PPT",
       "cost": 0.234, "message_count": 45,
       "created_at": "...", "updated_at": "..."}
    ],
    "total": 5, "page": 1, "page_size": 20
  }
}
```

---

### 3.7 知识库（文件管理）

> BM25 检索由 Agent 内部调用（`KnowledgeService.search()`）。前端只需管理文件。
> **文件存储**：文件放入 conversation 的 workspace 子目录，物理隔离。**索引**：BM25 按 user 全局索引（跨 conversation 共享检索）。

#### POST /api/knowledge/upload

```
multipart/form-data:
  user_id: 1
  conversation_id: 1          // 文件存入该 conversation 的 workspace/knowledge/
  files: [file1.pdf, file2.docx]

Response 201:
{
  "code": 0,
  "data": {
    "uploaded": [
      {"id": 1, "conversation_id": 1, "filename": "report.pdf",
       "file_type": "pdf", "file_size": 102400,
       "chunk_count": 15, "status": "indexed"}
    ],
    "failed": []
  }
}
```

处理流程：
1. 保存到 `workspace/{conversation_id}/knowledge/` 下
2. `parse_file()` → `chunk_text()` → DB 写入 chunks
3. `KnowledgeService.rebuild_user_index(user_id)` — 重建该用户全局 BM25 索引

#### GET /api/knowledge/files

```
Query: ?user_id=1              按用户筛选（必填）
Query: ?conversation_id=1      按会话筛选（可选，返回该会话 workspace 下的文件）
Query: ?type=pdf               文件类型
Query: ?source_type=upload     来源 (upload | web)
Query: ?status=indexed

Response 200:
{
  "code": 0,
  "data": {
    "items": [
      {"id": 1, "user_id": 1, "conversation_id": 1,
       "filename": "report.pdf", "file_type": "pdf",
       "file_size": 102400, "chunk_count": 15,
       "source_type": "upload", "status": "indexed", "created_at": "..."}
    ],
    "total": 3,
    "summary": {"total_files": 3, "total_size": 512000, "total_chunks": 42}
  }
}
```

#### DELETE /api/knowledge/files/{id}

删除文件 + 级联删除 chunks + 重建 BM25 索引。

```
Response 200:
{ "code": 0, "data": { "deleted": true, "file_id": 1 } }
```

---

### 3.8 工作空间 & 系统

#### GET /api/workspace/status

```
Query: ?user_id=1

Response 200:
{
  "code": 0,
  "data": {
    "workspace_root": "data/workspace",
    "conversations": [
      {"conversation_id": 1, "disk_usage": "2.3 MB",
       "file_counts": {"input": 3, "knowledge": 5, "output": 1}}
    ],
    "bm25_index": {
      "index_dir": "data/workspace/indexes",
      "indexes": [
        {"user_id": 1, "file": "bm25_index_1.pkl", "chunk_count": 72}
      ]
    }
  }
}
```

#### GET /api/config

返回非敏感配置（脱敏后）。

```
Response 200:
{
  "code": 0,
  "data": {
    "rag": {"algorithm": "bm25", "top_k": 5},
    "agent": {"outline": {"max_iterations": 5, "evaluation_threshold": 0.7}},
    "llm": {"provider": "deepseek", "model": "deepseek-v4-flash"},
    "web_search": {"enabled": true, "engine": "duckduckgo"}
  }
}
```

#### GET /api/health

```
Response 200:
{
  "status": "healthy",
  "db": "connected",
  "llm": "available",
  "bm25": "ready"
}
```

---

## 四、变更记录

| 变更 | 说明 |
|------|------|
| 移除 `POST /api/outline/generate` | Agent supervisor 通过 `POST /api/chat/send` 统一决策 |
| 移除 `PUT /api/outline/{id}` | 同上，用户反馈通过 chat/send 发送 |
| 移除 `POST /api/ppt/generate` | 同上 |
| 移除 `PUT /api/ppt/{id}` | 同上 |
| 大纲/PPT 端点全部改为只读 | GET 系列仅用于查看历史 |
| `POST /api/knowledge/upload` 新增 `conversation_id` | 文件存入 conversation workspace，索引全局 |
| `GET /api/knowledge/files` 新增 `conversation_id` 筛选 | 可按会话过滤文件 |
| 全部列表端点加 `user_id` | conversations / outlines / presentations / cost / knowledge files |
| 移除 `GET /api/web-resources` | WebResource 表已删除，网页内容统一走 KnowledgeService |
| Workspace BM25 路径 | `workspace/indexes/bm25_index_{user_id}.pkl` |
| SSE vs WebSocket | 选用 SSE，request-response 模式天然匹配 |
