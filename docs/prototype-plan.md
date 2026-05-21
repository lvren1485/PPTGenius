# PPTGenius Agent Prototype — 完整实施计划 (v3)

> 基于 [function-analysis.md](function-analysis.md) 的 PPT 生成 agent 原型开发计划
> 分支：`agent-prototype` | 版本：v3

---

## 一、背景

构建一个 PPT 生成 agent 原型，验证技术路线。

**核心要求：**
- Python 脚本，提供 CLI 入口（用 `uv run`）
- 系统输入：用户 prompt + 知识文件 + 可选会话 ID
- 系统输出：生成的 PPT 文件 + 工作总结/改进建议（合并报告）
- **所有 LLM 输出必须完整保存为日志，不得截断**
- 支持多轮对话与 PPT 修改（通过会话 ID 恢复上下文）
- 集成 RAG 知识库、结构化数据查询
- `src/` 下包名为 `agent/`（非 `pptgenius/`）
- 工具函数按类别独立文件，不挤在一个文件中
- 文件注册表使用 SQLite 而非 JSON
- 原型验证后丢弃，可大胆实验

---

## 二、项目结构

```
PPTGenius/
├── pyproject.toml
├── .env.example
├── src/agent/                           # 主包
│   ├── __init__.py → __main__.py        # CLI 入口
│   ├── cli.py                           # argparse + --session-id 参数
│   ├── config.py                        # 配置 + 技术路线开关
│   ├── logger.py                        # LogCapture 完整日志
│   ├── llm/                             # LLM 抽象层
│   ├── models/                          # pydantic 数据模型
│   ├── db/                              # SQLite 数据库层
│   ├── rag/                             # RAG 系统
│   │   └── parsers/                     # 各文件类型解析器
│   ├── agents/                          # Agent 定义
│   │   ├── orchestrator.py              # 顶层协调器
│   │   ├── ppter.py                     # Plan-then-Execute 主 agent
│   │   ├── reviewer.py                  # 审查 agent
│   │   └── tools/                       # 工具（按类别独立文件）
│   │       ├── registry.py              # 工具注册表
│   │       ├── knowledge.py             # 知识检索
│   │       ├── database.py              # 数据库查询
│   │       ├── search_web.py            # 网络搜索
│   │       ├── template.py              # 模板选择
│   │       ├── modification.py          # PPT 修改（内容+布局分开）
│   │       ├── generation.py            # PPT/图表/表格生成
│   │       ├── images.py                # 图片选择
│   │       └── planner.py               # 规划工具（create_plan, revise_plan）
│   └── ppt/                             # PPT 生成
│       ├── generator.py / slides.py / styles.py
│       └── templates.py / charts.py / images.py
│
├── resources/              ← RAG 源文件
├── data/
│   ├── vector_db/          ← 向量库
│   └── sqlite/
│       └── agent.db        ← 主数据库（会话+文件注册+结构化数据）
├── output/                 ← .pptx + _report.md
└── logs/
    ├── calls/              ← LLM 调用完整日志
    └── sessions/           ← 会话转录
```

---

## 三、系统 I/O

```
输入: [用户 prompt] + [--session-id] + [resources/ 文件]

输出:
  1. output/{session_id}.pptx
  2. output/{session_id}_report.md  (工作总结 + 改进建议，合并为一份)
```

**会话 ID：**
- 可选参数 `--session-id <uuid>`
- 未提供则自动生成 UUID v4
- 提供已存在的 ID → 恢复历史对话上下文
- 提供不存在的 ID → 创建新会话

---

## 四、数据库

统一使用 `data/sqlite/agent.db`，含 5 张表：

| 表 | 用途 |
|----|------|
| `sessions` | 会话元数据（ID、主题、状态、输出路径） |
| `turns` | 对话轮次（用户消息 + agent 回复） |
| `llm_calls` | LLM 调用记录（与 logs/calls/ 日志文件关联） |
| `tool_calls` | 工具调用记录（输入、输出、状态） |
| `file_registry` | **文件注册表**（替代 JSON，SQLite 便于存储和遍历） |

---

## 五、Agent 架构

### Agent 职责

| Agent | 说明 |
|-------|------|
| **Orchestrator** | 顶层协调：启动扫描 → 规划 → 派发 ppter → 派发 reviewer → 日志输出 |
| **PPT Agent (ppter)** | Plan-then-Execute 循环：先生成计划，再逐个完成 TODO |
| **Planner Sub-Agent** | ppter 的一部分，专门负责将任务分解为结构化 TodoList |
| **Review Agent** | 审查已生成 PPT → 输出合并报告（工作总结 + 改进建议） |

### 核心流程（Plan-then-Execute）

```
Orchestrator:
  1. 扫描 resources/，解析文件到 RAG + SQLite
  2. 加载/创建对话历史
  3. 规划阶段（ppter/planner）:
     LLM 分析用户请求 → 生成 Plan（TodoList）
     Plan 包含:
       - goal: 总体目标
       - items: 有序的 TodoItem 列表
         每个 TodoItem: {id, description, tools_needed, depends_on, status}
  4. 执行阶段（ppter ReAct）:
     for each todo_item in plan.items:
        当前 todo ← todo_item     ← 明确聚焦一个 todo
        while not todo.done:
            LLM 思考 + 选择工具
            执行工具 → 观察结果
            如需修正计划 → 调用 revise_plan 工具更新后续 todos
        标记 todo 完成
        保存中间状态到对话历史
  5. 审查阶段（reviewer）:
     分析生成的 PPT → output/{session_id}_report.md
  6. 输出 + 日志保存
```

### 工具分类（7 个文件，13 个工具）

| 文件 | 工具 | 说明 |
|------|------|------|
| `knowledge.py` | `query_knowledge_base` | 搜索 RAG 知识库 |
| `database.py` | `query_database` | 查询结构化数据 |
| `database.py` | `create_database` | 导入 CSV/xlsx |
| `search_web.py` | `search_web` | DuckDuckGo 搜索 |
| `template.py` | `select_template` | 选择/设计模板 |
| `generation.py` | `generate_ppt` | 生成 PPT |
| `generation.py` | `generate_chart` | matplotlib 图表 |
| `generation.py` | `generate_table` | 格式化表格 |
| `modification.py` | `modify_slide_content` | **修改内容**（文本/图片，不影响布局） |
| `modification.py` | `modify_slide_layout` | **修改布局**（位置/大小，不影响内容） |
| `images.py` | `select_image` | 查找图片 |
| `planner.py` | `create_plan` | 分析请求、生成 TodoList（规划阶段使用） |
| `planner.py` | `revise_plan` | 执行中修正剩余 plan 项 |

> 内容修改和布局修改分开为两个工具：操作 python-pptx 时改文本和改位置是完全不同的代码路径，分开更清晰、易调试。后续如需合并，加一个 `modify_slide` 包装函数即可。
>
> `optimization_suggestions` 不再作为独立工具，由 Review Agent 生成报告时自动完成。

### Plan 数据结构

```python
class TodoItem(BaseModel):
    id: int
    description: str          # 具体任务描述，如"从 RAG 知识库检索量子计算相关段落"
    tools_needed: list[str]   # 预计需要的工具
    depends_on: list[int]     # 依赖的 todo id（=0 表示无依赖）
    status: str = 'pending'   # pending | in_progress | completed | blocked

class Plan(BaseModel):
    goal: str                 # 总体目标
    items: list[TodoItem]     # 有序任务列表
    created_at: str
    revised_at: str | None    # 如有 revise_plan 调用则记录
```

---

## 六、技术路线实验

| 层级 | 路线 A | 路线 B | 路线 C | MVP |
|------|--------|--------|--------|-----|
| 向量库 | ChromaDB | FAISS | JSON | ChromaDB |
| Embedding | sentence-transformers | OpenAI | — | sentence-transformers |
| PDF 解析 | PyMuPDF | pdfplumber | — | PyMuPDF |
| LLM | OpenAI gpt-4o | Claude | ollama | gpt-4o |
| 图表 | matplotlib | plotly | — | matplotlib |
| 图片 | 内置库 | DuckDuckGo | — | 内置库+DDG |
| CLI | argparse | click | typer | argparse |

---

## 七、27 步实施计划

| # | 内容 |
|---|------|
| 1-2 | pyproject.toml + .env.example |
| 3-5 | 包初始化 + config + logger |
| 6-7 | LLM 抽象 + OpenAI 客户端 |
| 8-9 | 数据模型（outline + conversation） |
| 10-12 | SQLite 引擎 + 对话 CRUD + 结构化数据 |
| 13-18 | RAG：scanner → parsers → chunker → embedder → vector_store |
| 19 | CLI（含 --session-id） |
| 20-21 | 工具实现（7文件） + 注册表 |
| 22-24 | ppter + reviewer + orchestrator |
| 25-26 | PPT 模块（样式/模板/幻灯片/图表/图片/生成器） |
| 27 | 端到端测试 |

---

## 八、验证

1. `uv sync` 安装成功
2. `uv run pptgenius "量子计算"` → `output/` 有 .pptx + _report.md
3. `--session-id` 可恢复多轮对话
4. `logs/calls/` 日志完整无截断
5. `agent.db` 记录完整

---

## 九、开发约束

### 1. 代码文件不超过 300 行
- 每个 `.py` 文件严格控制在 300 行以内
- 超出则拆分（例如 `slides.py` 可拆为 `slides_title.py`, `slides_content.py`）
- 保持函数短小，一个函数只做一件事

### 2. API Key 策略
- **当前阶段：** 无需 API key。LLM 调用先用 mock/stub，等模块完成后通知用户配置
- **测试前提醒：** 在进行端到端测试前，会提醒用户将 OpenAI API key 写入 `.env`
- 用户目前不会提供 API key，因此所有涉及 LLM 调用的代码需支持 dry-run 模式或 mock

### 3. 按模块提交 Git Commit
| 提交时机 | 包含内容 |
|----------|----------|
| Commit 1 | 项目骨架：pyproject.toml, \_\_init\_\_, config, logger |
| Commit 2 | LLM 抽象层：base.py + openai_client.py |
| Commit 3 | 数据模型：outline.py + conversation.py |
| Commit 4 | 数据库层：engine.py + conversation.py + structured_data.py |
| Commit 5 | RAG 系统：scanner + parsers + chunker + embedder + vector_store |
| Commit 6 | CLI + 工具实现：cli.py + tools/\* |
| Commit 7 | Agent 系统：ppter.py + reviewer.py + orchestrator.py |
| Commit 8 | PPT 生成模块：ppt/\* |
| Commit 9 | 端到端测试 + 文档更新 |

---

## 十、当前状态

> 原型已完成 9 个 Commit 的全部实施。`uv run pptgenius "主题"` 可正常运行，生成 PPT + 报告 + 完整日志。

## 十一、后续计划

如需继续迭代：
- **填写 API key** 到 `.env` 后，LLM 调用将从 Mock 切换为真实模型
- **更多布局类型**：增加两栏式、图文混排等 layout
- **更多模板**：添加更多视觉风格
- **多轮对话**：通过 `--session-id` 恢复历史，修改已有 PPT
