# PPTGenius API Design

> 版本: 0.3.0 | 日期: 2026-06-17

---

## 目录

1. [API 总览](#1-api-总览)
2. [Auth 模块](#2-auth-模块)
3. [Chat 模块](#3-chat-模块)
4. [Conversations 模块](#4-conversations-模块)
5. [Outline 模块](#5-outline-模块)
6. [PPT 模块](#6-ppt-模块)
7. [Export 模块](#7-export-模块)
8. [Knowledge 模块](#8-knowledge-模块)
9. [User / Workspace / System 模块](#9-user--workspace--system-模块)
10. [SSE 事件规范](#10-sse-事件规范)
11. [通用响应格式](#11-通用响应格式)

---

## 1. API 总览

| 模块 | 前缀 | 文件 |
|------|------|------|
| Auth | `/api/auth` | `api/auth.py` |
| Conversations | `/api/conversations` | `api/conversations.py` |
| Chat | `/api/chat` | `api/chat.py` |
| Outline | `/api/outlines` | `api/outline.py` |
| PPT | `/api/presentations` | `api/ppt.py` |
| Snapshot | `/api/snapshots` | `api/snapshot.py` |
| Export | `/api/export` | `api/export.py` |
| Knowledge | `/api/knowledge` | `api/knowledge.py` |
| User | `/api/user` | `api/user.py` |
| Workspace | `/api/workspace` | `api/workspace.py` |
| Cost | `/api/cost` | `api/cost.py` |
| System | `/api` | `api/system.py` |

所有请求需 `Authorization: Bearer <token>` (除 `/api/auth/login`, `/api/auth/register`)。

---

## 2. Auth 模块

### POST `/api/auth/register`
```json
// Request
{ "name": "user", "password": "123456" }
// Response
{ "code": 0, "data": { "token": "...", "user_id": 1, "name": "user" } }
```

### POST `/api/auth/login`
```json
// Request
{ "name": "user", "password": "123456" }
// Response
{ "code": 0, "data": { "token": "...", "user_id": 1, "name": "user" } }
```

### JWT: HS256, 7天 TTL. Secret key 从 `config.llm.api_key` 派生。

---

## 3. Chat 模块

### POST `/api/chat/send` (SSE)
```
Request:  { "user_id": 1, "conversation_id": 5, "message": "做一个PPT" }
Response: text/event-stream (见 §10 SSE 事件规范)
```

### POST `/api/chat/{conversation_id}/cancel`
中断正在进行的 SSE 流。

---

## 4. Conversations 模块

### GET `/api/conversations?user_id=&status=active`
```json
{ "code": 0, "data": { "items": [{ "id": 1, "title": "...", "status": "active",
    "message_count": 15, "estimated_cost": 0.12, "updated_at": "..." }] } }
```

### POST `/api/conversations`
```json
// Request: { "user_id": 1, "title": "新对话" }
// Response: { "code": 0, "data": { "id": 5 } }
```

### GET `/api/conversations/{id}`
返回会话详情 + messages 列表。

### PATCH `/api/conversations/{id}/archive`
归档（软删除）。

### DELETE `/api/conversations/{id}`
硬删除。

---

## 5. Outline 模块

### GET `/api/outlines?user_id=`
大纲列表，每项含 `{id, title, status, version, slide_count, eval_score}`。

### GET `/api/outline/{id}`
大纲详情，含 sections + slides。

### DELETE `/api/outline/{id}`
软删除（status="deleted"）。

---

## 6. PPT 模块

### GET `/api/presentations?user_id=`
PPT 列表，每项含 `{id, title, status, version, outline_version, slide_count}`。

### GET `/api/ppt/{id}`
PPT 详情，含 `{style_name, status, version, outline_version, slide_count}`。

### GET `/api/ppt/{id}/snapshots`
快照列表 `[{id, version, created_at}]`。

---

## 7. Export 模块

### GET `/api/export/outline/{snapshot_id}/content`
返回 `{filename, content: "markdown文本"}`。

### GET `/api/export/presentation/{snapshot_id}/content`
返回 `{filename, content: "base64编码的pptx"}`。

### GET `/api/export/outline-snapshots/{outline_id}`
大纲的所有快照列表。

---

## 8. Knowledge 模块

### POST `/api/knowledge/upload`
```
multipart/form-data: user_id, conversation_id, files[]
→ 200: { "code": 0, "data": { "uploaded": [{ "id": 1, "filename": "..." }] } }
```

### GET `/api/knowledge/files?user_id=&conversation_id=`
文件列表。

### DELETE `/api/knowledge/files/{file_id}`
删除文件 + chunks。

---

## 9. User / Workspace / System 模块

### GET `/api/user/settings`
`{ "web_search_enabled": true, "rag_mode": "user" }`

### PUT `/api/user/settings`
`{ "web_search_enabled": false, "rag_mode": "conversation" }`

### GET `/api/workspace/files?conversation_id=`
列出会话 workspace 文件。

### GET `/api/config`
前端读取的公开配置（rag, agent, llm, web_search 摘要）。

### GET `/api/health`
`{ "status": "healthy", "db": "connected", "llm": "configured", "bm25": "ready" }`

### GET `/api/cost?user_id=`
用户费用统计。

---

## 10. SSE 事件规范

**协议:** `POST /api/chat/send` → `text/event-stream`

每帧格式:
```
event: message
data: {"type": "...", ...}
```

| type | 字段 | 说明 |
|------|------|------|
| `master_start` | — | Master Agent 开始处理 |
| `tool_start` | `tool`, `args` | 工具调用开始 |
| `tool_end` | `tool`, `result`, `result_len` | 工具调用结束 |
| `tool_error` | `tool`, `error` | 工具异常 |
| `document` | `doc_type`, `snapshot_id`, `title`, `version` | 产出大纲/PPT |
| `master_reply` | `reply` | Master 文本回复 |
| `master_done` | — | Master 本轮结束 |

终端事件:
```
event: done     → 流正常结束
event: error    → { "message": "..." }
```

---

## 11. 通用响应格式

```json
// 成功
{ "code": 0, "data": { ... } }

// 异常 (HTTP 4xx/5xx)
{ "detail": { "message": "错误描述" } }
```
