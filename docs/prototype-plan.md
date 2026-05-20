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
│   │   ├── ppter.py                     # ReAct 主 agent
│   │   ├── reviewer.py                  # 审查 agent
│   │   └── tools/                       # 工具（按类别独立文件）
│   │       ├── registry.py              # 工具注册表
│   │       ├── knowledge.py             # 知识检索
│   │       ├── database.py              # 数据库查询
│   │       ├── search_web.py            # 网络搜索
│   │       ├── template.py              # 模板选择
│   │       ├── modification.py          # PPT 修改
│   │       ├── generation.py            # PPT/图表/表格生成
│   │       └── images.py                # 图片选择
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

| Agent | 说明 |
|-------|------|
| **Orchestrator** | 顶层协调：启动扫描 → 派发 ppter → 派发 reviewer → 日志输出 |
| **PPT Agent (ppter)** | ReAct 循环：LLM推理 + 12工具调用 → 生成 PPT |
| **Review Agent** | 审查已生成 PPT → 输出合并报告（工作总结 + 改进建议） |

**工具分类（7 个文件，12 个工具）：**

| 文件 | 工具 |
|------|------|
| `knowledge.py` | `query_knowledge_base` |
| `database.py` | `query_database`, `create_database` |
| `search_web.py` | `search_web` |
| `template.py` | `select_template` |
| `generation.py` | `generate_ppt`, `generate_chart`, `generate_table` |
| `modification.py` | `modify_slide_content`, `modify_slide_layout` |
| `images.py` | `select_image` |

> `optimization_suggestions` 不再作为独立工具，由 Review Agent 生成报告时自动完成。

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

## 九、当前状态

✅ 规划完成，等待实施（明天输入 `continue` 继续）。
