# Outline Agent 实现文档

## 1. 概览

Outline Agent 是 PPTGenius 的核心子 Agent，负责 PPT 大纲的生成与迭代优化。采用 **Generator-Evaluator 循环架构**，基于 LangGraph 构建。

### 文件结构

```
agent/outline/
├── __init__.py      # exports: build_outline_graph, OutlineState
├── state.py         # OutlineState TypedDict
├── prompts.py       # Prompt 加载与构建
├── generator.py     # Generator 节点（LLM + 4 tools）
├── evaluator.py     # Evaluator 节点（LLM + 1 tool）
└── graph.py         # LangGraph 图构建 + 路由逻辑 + finalize 节点
```

## 2. Agent 图结构

```
ENTRY ──[no outline_id]──▶ generator ──▶ evaluator ──[stop?]──▶ finalize ──▶ END
    │                                    ▲        │
    └──[has outline_id]──▶ evaluator ────┘   [continue]──▶ generator
```

### 路由逻辑

| 条件 | 路由目标 |
|------|---------|
| `outline_id is None` | generator（新建） |
| `outline_id` 有值 + `evaluated=False` | evaluator（先评分） |
| `outline_id` 有值 + `evaluated=True` | generator（修改模式） |
| evaluator 后满足停止条件 | finalize → END |
| evaluator 后不满足停止条件 | generator（继续迭代） |

### 停止模式

| 模式 | 配置值 | 停止条件 |
|------|--------|---------|
| Max Iteration | `max_iteration` | `iteration >= max_iterations` |
| Pass Score | `pass_score` | `eval_score >= pass_score` |
| Mix（默认） | `mix` | 任一条件满足 |

配置项位于 `config.yaml → agent.outline`。

## 3. State 设计

```python
class OutlineState(TypedDict):
    user_id: int
    conversation_id: int
    query: str                          # 当前用户消息/任务描述
    outline_id: int | None              # 当前大纲ID，None=新建
    evaluated: bool                     # 控制路由
    iteration: int                      # Generator 运行次数
    eval_score: float | None            # 最新评分（0-10）
    eval_suggestions: str               # 最新改进建议
    mode: str                           # 停止模式
    max_iterations: int
    pass_score: float
    design_rationale: str               # 最新一轮的设计思路
    design_rationales: list[str]        # 所有轮次的设计思路（累加）
    final_outline_data: dict | None     # finalize 节点打包的大纲数据
    messages: list[BaseMessage]         # LLM 消息历史（累加）
```

### Memory 存储点

| 存储点 | 存储内容 | 位置 |
|--------|---------|------|
| Generator 调用 write_outline | outline + outline_slides 写入 DB | generator.py::_make_write_outline |
| Evaluator 调用 submit_evaluation | eval_score 写入 outlines 表 | evaluator.py::_make_submit_evaluation |
| finalize 节点 | 从 DB 读取最终大纲，打包到 state.final_outline_data | graph.py::finalize_node |
| design_rationales | 每轮 Generator 的 rationale 累加到 state | generator_node return |
| TokenCounter | 每次 LLM 调用累加 token 用量 | generator_node / evaluator_node |

## 4. Generator 节点

### 工具列表

| 工具 | 功能 | 来源 |
|------|------|------|
| `search_knowledge` | BM25 检索用户知识库 | KnowledgeService.search |
| `search_web` | 网络搜索（DuckDuckGo/SearXNG） | WebSearchService.search |
| `fetch_web` | 抓取网页并索引 | WebSearchService.fetch_and_ingest |
| `write_outline` | **终止工具**：写入 outline + slides 到 DB | Database.create_outline / replace_outline_slides |

### 执行流程

```
SystemMessage + HumanMessage
    → LLM (with tools)
    → [tool_calls?]
        → execute tools (search / fetch / write)
        → ToolMessage → back to LLM
    → [write_outline called?]
        → YES: return updated state
        → NO / max_turns exceeded: break with warning
```

### Slide content_json 结构

每个 slide 的 content_json 包含：
- `main_points`: 核心观点列表
- `detailed_content`: 详细文本（PPT 生成器直接使用）
- `key_data`: 关键数据
- `visual_note`: 可视化建议
- `recommended_ppt_format`: 推荐 PPT 排版格式（bullet_list / two_column / flowchart / chart / timeline / comparison 等 14 种）

### 错误处理

- LLM 调用失败：记录日志，continue 下一轮
- 工具调用失败：返回 `{"error": ...}` 的 ToolMessage，不中断流程
- write_outline 解析失败：记录日志，继续（不 break）
- 超过 max_turns（20）：记录错误日志，返回已获取的状态

## 5. Evaluator 节点

### 工具列表

| 工具 | 功能 | 来源 |
|------|------|------|
| `submit_evaluation` | **终止工具**：提交评分 + 建议，写入 outline.eval_score | Database.update_outline_eval |

### 评分维度

| 维度 | 权重 | 满分 | 说明 |
|------|------|------|------|
| structure_clarity | 1.0 | 10 | 结构清楚度 |
| logic_coherence | 1.0 | 10 | 逻辑通畅度 |
| comprehensiveness | 1.0 | 10 | 展示全面度 |
| visual_diversity | 1.0 | 10 | 可视化多样度 |

总分 = (structure_clarity + logic_coherence + comprehensiveness + visual_diversity) / 4

### 错误处理

- outline_id 为 None：返回 eval_score=0.0，evaluated=True
- outline 未找到：返回 eval_score=0.0，evaluated=True
- LLM 调用失败：记录日志，continue 下一轮
- 工具调用失败：返回 error ToolMessage，不中断流程

## 6. Finalize 节点

在 Evaluator 判定停止后、END 之前执行。

### 职责

1. 从 DB 读取最终大纲 + slides
2. 打包为 `final_outline_data`（包含完整 slide 数据）
3. 保留 `design_rationales` 列表

Coordinator 通过 `astream_events` 捕获 `on_chain_end` 事件（name="finalize"），将 outline 数据直接通过 SSE 发送给前端，**不再由 Coordinator 重新读取**。

## 7. Token 计费

使用 `infrastructure.utils.TokenCounter`：

- `TokenCounter.for_conversation(conv_id)` 获取/创建计数器
- 每次 LLM `ainvoke` 后调用 `tc.add(response.usage_metadata)`
- 支持 DeepSeek cache hit/miss 分开计价
- 计价表：
  - deepseek-v4-flash: cache_hit=0.02, cache_miss=1.00, output=2.00 CNY/1M tokens
  - deepseek-v4-pro: cache_hit=0.025, cache_miss=3.00, output=6.00 CNY/1M tokens

## 8. Traceability

所有关键路径的追踪点：

1. **Generator LLM 调用前**：日志记录 `is_revision`、`outline_id`、`iteration`
2. **write_outline 调用**：日志记录 `outline_id`、`slide_count`、`created/revised`
3. **Evaluator LLM 调用前**：日志记录 `outline_id`
4. **submit_evaluation 调用**：日志记录 `outline_id`、`total_score`
5. **路由决策**：`_route_entry` 和 `_should_continue` 记录日志
6. **Token 累计**：每次 LLM 调用后 TokenCounter 记录 debug 日志
7. **finalize 节点**：打包 `final_outline_data`
