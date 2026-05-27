# Coordinator Agent 实现文档

## 1. 概览

Coordinator Agent 是 PPTGenius 的顶层调度 Agent，负责**分析用户意图**并**分派给子 Agent**（Outline Agent / PPT Agent）。它读取对话历史、当前状态，使用 LLM 进行智能路由。

### 文件结构

```
agent/
├── __init__.py              # exports: run_coordinator
├── coordinator.py           # 意图分类 + 子 Agent 分派 + SSE 流式输出
├── common/
│   └── langchain_adapter.py # DeepSeek 适配补丁
├── outline/                 # Generator-Evaluator 大纲 Agent
└── ppt/                     # PPT 生成 Agent（开发中占位）
```

## 2. 协调流程

```
用户消息
    → 加载对话状态（outline、PPT、历史消息）
    → 构建上下文（状态摘要 + 最近 10 条消息）
    → LLM 意图分类（structured output → CoordinatorDecision）
    → 分派子 Agent
        ├─ generate_outline  → Outline Graph（新建）
        ├─ modify_outline    → Outline Graph（修改，skip evaluator）
        ├─ generate_ppt      → PPT Graph（开发中）
        └─ modify_ppt        → PPT Graph（开发中）
    → 流式输出 SSE 事件（progress / outline / phase / tokens）
    → 存储 Assistant Message 到 DB
    → 输出 Token 用量摘要
```

## 3. 意图分类

### 分类模型

使用 `ChatOpenAI.with_structured_output(CoordinatorDecision)` 进行 LLM 驱动的意图识别，**不使用字符串匹配**。

```python
class CoordinatorDecision(BaseModel):
    task: Literal["generate_outline", "modify_outline", "generate_ppt", "modify_ppt"]
    reasoning: str  # 判断依据
```

### 分类依据

LLM 综合以下信息做出判断：

1. **当前状态**（有/无 outline、有/无 PPT）
2. **对话历史**（最近 10 条消息摘要）
3. **用户最新消息**（显式意图 + 隐式意图）

### Prompt（resources/prompts/coordinator_system.txt）

定义了 4 种任务的路由规则：
- 关键词信号（"重写" → generate_outline 即使已有大纲）
- 状态约束（无 PPT 不能选 modify_ppt）
- 安全偏向（不确定时偏修改而非重新生成）

### Cache 触发

Coordinator 将最近 10 条对话历史作为上下文传入 LLM 调用，以便 DeepSeek 的上下文缓存机制命中。

## 4. 状态加载

### 从 DB 读取

| 数据 | Repository 方法 |
|------|----------------|
| Conversation | `db.get_conversation(conv_id)` |
| Outlines | `db.list_outlines_by_conversation(conv_id)` |
| Presentations | `db.list_presentations_by_conversation(conv_id)` |
| Messages（历史） | `db.get_messages_by_conversation(conv_id)` |

### get_conversation_state 工具

Coordinator 内置了一个 LangChain Tool，可供 LLM 在分类时调用：

```python
@tool
async def get_conversation_state(dummy: str = "") -> str:
    """Get the current conversation's PPT and outline status."""
```

返回 JSON 格式的状态摘要（has_outline、outline_count、latest_outline、has_ppt、ppt_count、latest_ppt）。

## 5. 子 Agent 分派

### Outline Agent 分派

```python
async def _run_outline(db, user_id, conversation_id, query,
                       existing_outline, is_modify):
```

- **新建大纲**：`outline_id=None, evaluated=False` → 图路由到 generator
- **修改大纲**：`outline_id=existing, evaluated=True` → 图路由到 generator（跳过 evaluator）

### PPT Agent 分派

```python
async def _run_ppt(db, user_id, conversation_id, query,
                   outline, existing_ppt):
```

- 无大纲时返回错误
- 占位实现：返回"开发中"提示

## 6. SSE 流式输出

### 事件类型

| 事件 | 触发时机 | 数据 |
|------|---------|------|
| `progress` | 工具调用开始/结束、决策完成 | `{step, detail, pct, ...}` |
| `phase` | 阶段切换 | `{phase, message}` |
| `outline` | write_outline 完成 / finalize 完成 | `{outline_id, title, slides, ...}` |
| `tokens` | 子 Agent 完成 | `TokenCounter.snapshot()` |
| `message_stored` | AIMessage 写入 DB 后 | `{role, length}` |
| `done` | 全部完成（chat.py） | `{elapsed_seconds, token_usage}` |
| `error` | 错误 | `{code, message, retryable}` |

### 流式架构

```
Coordinator._run_outline
    → graph.astream_events(state, config, version="v2")
        → on_tool_start  → _tool_start_sse  → yield SSE
        → on_tool_end    → _tool_end_sse    → yield SSE
        → on_chain_end   → finalize node    → yield outline SSE
    → catch Exception   → error recovery   → yield recovered outline
```

### 前端数据直达

**关键设计**：Outline Graph 的 `finalize` 节点直接从 DB 读取最终大纲并打包到 `state.final_outline_data`。Coordinator 通过 `astream_events.on_chain_end(name="finalize")` 捕获该数据并通过 SSE 直传给前端。**Coordinator 不重新读取大纲**。

## 7. 消息持久化

### HumanMessage

在 `chat.py::chat_send` 中，用户消息到达后立即存储：

```python
await db.create_human_message(req.conversation_id, req.message)
```

### AIMessage

在 `coordinator.py::run_coordinator` 完成子 Agent 调用后存储：

```python
await db.create_message(
    conversation_id=conversation_id,
    role="assistant",
    content=assistant_content,  # 包含决策依据 + 大纲摘要 + design_rationales
    estimated_cost=snapshot["estimated_cost_cny"],
)
```

Assistant 消息内容包括：
1. 执行的任务类型
2. 决策依据（reasoning）
3. 大纲摘要（标题、ID、版本、评分）
4. 每轮 Generator 的设计思路（design_rationales）

## 8. 错误恢复

### 三层防护

| 层级 | 防护措施 | 位置 |
|------|---------|------|
| 工具调用 | try/except 捕获，返回 error ToolMessage，不中断 LLM 循环 | generator_node / evaluator_node |
| LLM 调用 | try/except 捕获，continue 下一轮 | generator_node / evaluator_node |
| 图执行 | try/except 捕获，尝试读取已生成的大纲并发送 | _run_outline |

### 恢复策略

子 Agent 执行出错时：
1. 查询 DB 中该对话的最新 outline
2. 如果存在，读取并封装为 outline SSE 事件发送
3. 如果不存在，发送 error 事件

## 9. Token 计费

使用 `infrastructure.utils.TokenCounter`：

- 每次 LLM `ainvoke` 后调用 `tc.add(response.usage_metadata)`
- 支持 DeepSeek cache hit/miss 分开计价
- Coordinator 完成时分两个渠道输出：
  1. `tokens` SSE 事件（子 Agent 完成后）
  2. `done` 事件中的 `token_usage` 字段（chat.py）

## 10. design_rationales 传递链

```
Generator Round 1 → design_rationale_1 → state.design_rationales[0]
Generator Round 2 → design_rationale_2 → state.design_rationales[1]
...
finalize node → state.design_rationales (accumulated)
Coordinator → _rationale_store (module-level list)
Coordinator._build_assistant_content → 写入 AIMessage content
前端展示 ← AIMessage (content contains all rationales)
```

## 11. Traceability

| 追踪点 | 日志内容 | 位置 |
|--------|---------|------|
| 意图分类 | `decision: {task} (reason: {reasoning})` | _classify_intent |
| 子 Agent 启动 | `phase` SSE 事件 | _run_outline / _run_ppt |
| 工具调用 | `on_tool_start` / `on_tool_end` → SSE | _tool_start_sse / _tool_end_sse |
| Token 累计 | debug 日志（每次 LLM 调用） | TokenCounter.add |
| 消息存储 | `message_stored` SSE 事件 | run_coordinator |
| 错误 | exception 日志 + error SSE 事件 | 各 try/except 块 |
