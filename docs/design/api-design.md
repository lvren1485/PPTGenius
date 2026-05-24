# PPTGenius API 设计

> RESTful API，FastAPI 实现，SSE 流式响应
> 日期：2026-06-03

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

单人网站暂不设认证。各接口暂用固定 user_id=1。后续如需认证，加 `Authorization: Bearer <token>` Header，从 token 解析 user_id。

---

## 二、端点总览

```
POST   /api/conversations              创建会话
GET    /api/conversations              会话列表
GET    /api/conversations/{id}         会话详情
DELETE /api/conversations/{id}         删除会话

POST   /api/chat/send                  发送消息（SSE 流式）

POST   /api/outline/generate           生成大纲
GET    /api/outline/{id}               获取大纲
PUT    /api/outline/{id}               用户反馈修改大纲

POST   /api/ppt/generate               生成 PPT
GET    /api/ppt/{id}                   获取 PPT 详情
GET    /api/ppt/{id}/download          下载 PPT
PUT    /api/ppt/{id}                   用户反馈修改 PPT

POST   /api/knowledge/upload           上传文件
GET    /api/knowledge/files            文件列表
DELETE /api/knowledge/files/{id}       删除文件
POST   /api/knowledge/scrape           网页爬取

GET    /api/workspace/status           工作空间状态
POST   /api/workspace/cleanup          清理

GET    /api/config                     获取配置
GET    /api/health                     健康检查
```

---

## 三、详细接口

### 3.1 会话

#### POST /api/conversations

```
Request:  { "title": "关于AI的PPT" }

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
Query: ?status=active&page=1&page_size=20

Response 200:
{
  "code": 0,
  "data": {
    "items": [{
      "id": 1, "title": "关于AI的PPT", "status": "active",
      "current_phase": "outline", "message_count": 5,
      "estimated_cost": 0.032, "created_at": "...", "updated_at": "..."
    }],
    "total": 1, "page": 1, "page_size": 20
  }
}
```

#### GET /api/conversations/{id}

返回会话 + 消息列表 + 关联的大纲和 PPT。

#### DELETE /api/conversations/{id}

软删除（status=archived），或硬删除连带 workspace 文件。

---

### 3.2 对话 — POST /api/chat/send

核心接口。SSE 流式返回进度和大纲/PPT 结果。

```
Request:
{
  "conversation_id": 1,
  "message": "我想做一个关于Python数据分析的PPT"
}

Response: text/event-stream

event: phase
data: {"phase": "outline", "message": "开始生成大纲..."}

event: progress
data: {"step": "generating", "detail": "正在生成第1版大纲...", "pct": 10}

event: progress
data: {"step": "evaluating", "detail": "评估评分 0.72，正在修改...", "pct": 30}

event: outline
data: {"outline_id": 1, "title": "Python数据分析入门", "slides": [...], "eval_score": 0.85}

event: phase
data: {"phase": "waiting_user", "message": "请确认或修改大纲"}

--- 用户确认后继续 ---

event: phase
data: {"phase": "ppt", "message": "开始生成PPT..."}

event: progress
data: {"step": "generating_slides", "detail": "3/12...", "pct": 60}

event: ppt_ready
data: {"presentation_id": 1, "file_path": "...", "slide_count": 12, "download_url": "/api/ppt/1/download"}

event: done
data: {"estimated_cost": 0.0062, "elapsed_seconds": 45.2}

event: error
data: {"code": 40201, "message": "LLM timeout", "retry": true}

event: budget
data: {"total_tokens": 5000, "estimated_cost": 0.25}
```

---

### 3.3 大纲

#### POST /api/outline/generate — 生成

```
Request:
{
  "conversation_id": 1,
  "message": "做一个Python数据分析PPT"      // 用户原始/最新消息
}
```

触发 LangGraph Outline Agent 的 generator-evaluator 循环。

#### GET /api/outline/{id} — 获取

返回当前大纲 + 版本历史。

#### PUT /api/outline/{id} — 用户反馈（简化版）

只接受 message，由 LangGraph 用户反馈节点处理。

```
Request:
{
  "message": "增加一个实战案例页，删掉数据清洗部分"
}

Response 200:
{
  "code": 0,
  "data": {
    "outline_id": 1,
    "version": 2,
    "status": "review",
    "eval_score": 0.90,
    "slides": [ ... ]      // Agent 根据 message 重新生成的大纲
  }
}
```

> 不提供逐页精确修改 API。前端只需传用户反馈文本即可，Agent 自行理解意图并调整大纲。

---

### 3.4 PPT

#### POST /api/ppt/generate — 生成

```
Request:
{
  "conversation_id": 1,
  "outline_id": 1,
  "language": "zh"
}
```

> 不传入 template。配色/布局由 layout_agent 每次动态生成。
> 返回 SSE 流式（同 chat/send 的 ppt 阶段）。

#### GET /api/ppt/{id} — 详情

```
Response 200:
{
  "code": 0,
  "data": {
    "id": 1,
    "file_path": "...", "file_size": 46780, "slide_count": 12,
    "status": "completed",
    "slides": [{
      "slide_index": 0, "layout_type": "title",
      "color_scheme": {"primary": "#1a73e8", "accent": "#ea4335", "bg": "#ffffff"},
      "text_content": {"title": "Python 数据分析"},
      "image_paths": [], "chart_paths": []
    }]
  }
}
```

#### GET /api/ppt/{id}/download — 下载

返回 `.pptx` 文件流。

#### PUT /api/ppt/{id} — 用户反馈修改（简化版）

只接受 message。

```
Request:
{
  "message": "第3页太拥挤了，拆成两页；整体颜色改暖色系"
}

Response 200:
{
  "code": 0,
  "data": {
    "id": 1,
    "status": "modified",
    "file_path": "data/workspace/1/output/xxx_v2.pptx",
    "slide_count": 13    // 拆页后 +1
  }
}
```

> LangGraph PPT Agent 的用户反馈节点根据 message 重新生成/修改相关 slide。不提供逐页精确修改 API，降低前端复杂度。

---

### 3.5 知识库

#### POST /api/knowledge/upload

```
multipart/form-data:
  files: [file1.pdf, file2.docx]

Response 201:
{
  "code": 0,
  "data": {
    "uploaded": [
      {"id": 1, "filename": "report.pdf", "file_type": "pdf",
       "file_size": 102400, "status": "indexing"}
    ],
    "failed": []
  }
}
```

#### GET /api/knowledge/files

```
Query: ?type=pdf

Response: { "items": [...], "total_file_size": ..., "total_chunks": ... }
```

#### DELETE /api/knowledge/files/{id}

删除文件 + 对应 chunks，重建 BM25 索引。

#### POST /api/knowledge/scrape

```
Request:  { "url": "https://..." }

Response: { "id": 5, "url": "...", "title": "...", "status": "indexed" }
```

---

### 3.6 工作空间 & 系统

#### GET /api/workspace/status

```
Response:
{
  "workspace_path": "data/workspace/1/",
  "disk_usage": "2.3 MB",
  "file_counts": {"input": 3, "knowledge": 5, "output": 1},
  "bm25_index": {"exists": true, "files_indexed": 5, "total_chunks": 72}
}
```

#### POST /api/workspace/cleanup

```
Request:  { "clean_type": "temp" }    // temp | all
```

#### GET /api/config

返回 rag/agent/llm 等非敏感配置 (从 config.yaml)。

#### GET /api/health

```
{ "status": "healthy", "db": "connected", "llm": "available", "bm25": "ready" }
```

---

## 四、变更记录 (相对上一版)

| 变更 | 说明 |
|------|------|
| POST /api/outline/generate | 移除 `use_knowledge_base` 参数，简化为传 message |
| PUT /api/outline/{id} | 移除了逐页修改的 `modifications[]`，只接受 `message` 文本 |
| POST /api/ppt/generate | 移除 `template` 参数 |
| PUT /api/ppt/{id} | 移除了逐页修改的 `modifications[]`，只接受 `message` 文本 |
| presentation_slides 响应 | 新增 `color_scheme`，移除 `template_name` |
| 整体 | 所有接口暂不要求认证 Header |
