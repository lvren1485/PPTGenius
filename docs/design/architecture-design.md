# PPTGenius 架构设计

> BM25 检索 + LangGraph Agent + FastAPI 单人网站
> 日期：2026-06-04

---

## 一、技术选型

| 层面 | 选择 | 理由 |
|------|------|------|
| 语言 | Python 3.12+ | uv 管理 |
| Web 框架 | FastAPI | 异步支持好，自动生成 API 文档 |
| Agent 框架 | LangGraph + LangChain create_agent | ReAct tool-calling + StateGraph 编排 |
| RAG 检索 | BM25（rank_bm25） | 文件量不大，无需向量库 |
| BM25 持久化 | pickle 序列化 | 启动时加载，免重建 |
| 数据库 | MySQL + asyncmy | SQLAlchemy async engine |
| 配置 | .env + config.yaml | 密钥 env，业务 yaml |
| LLM | DeepSeek API | OpenAI 兼容 SDK + reasoning_content 适配补丁 |
| PPT 引擎 | python-pptx | 成熟稳定，原生图表/表格/形状 |
| 图表 | python-pptx 原生图表 | 非 matplotlib→PNG，原生图表可编辑+矢量 |
| SVG 处理 | cairosvg → PNG | python-pptx 不支持 SVG |
| 文件解析 | python-docx, PyPDF2, openpyxl, pandas | 多格式文件解析 |
| 包管理 | uv | |

---

## 二、整体架构

```
浏览器 ──HTTP/SSE──► FastAPI (src/pptgenius/main.py)
                          │
         ┌────────────────┼────────────────┐
         │                │                │
    ┌─ api/ ─┐    ┌─ agent/ ─────┐  ┌─ infrastructure/ ─┐
    │ routes │    │ coordinator  │  │ config  │ rag(BM25)│
    │ deps   │    │ outline      │  │ db      │ ppt_engine│
    │ SSE    │    │ ppt          │  │workspace│ utils     │
    └────────┘    │ common       │  └────────────────────┘
                  └──────────────┘
         │                │                │
         └────────────────┼────────────────┘
                          │
              ┌─ resources/ ───────┐  ┌─ tests/ ────────┐
              │ prompts/           │  │ test_api/        │
              │ instructions/      │  │ test_agent/      │
              │ layouts/           │  │ test_rag/        │
              │ fonts/             │  │ test_ppt_engine/ │
              │ tabler/            │  └──────────────────┘
              └────────────────────┘
```

三层依赖：api → agent → infrastructure。（infrastructure 不依赖上层）

**Coordinator 统一调度**：前端只通过 `POST /api/chat/send` 发送消息，Coordinator Agent 分类意图后分发到大纲或 PPT 子 Agent。

```
用户消息 → POST /api/chat/send → Coordinator Agent (意图分类)
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                                    ▼
           Outline Agent                        PPT Agent
           (generator-evaluator loop)           (两阶段流水线)
```

---

## 三、文件结构

```
backend/
├── main.py                          # 薄启动器: from pptgenius.main import main
├── pyproject.toml
├── uv.lock
├── .env
├── config.yaml
│
└── src/pptgenius/
    ├── __init__.py
    ├── main.py                      # FastAPI app = create_app() + uvicorn
    │
    ├── api/                         # ═══ Web API 层 ═══
    │   ├── __init__.py
    │   ├── router.py                # 注册所有子路由
    │   ├── deps.py                  # FastAPI Depends: DB, KnowledgeService, WorkspaceManager
    │   ├── schemas.py               # Pydantic request/response 模型
    │   ├── chat.py                  # POST /api/chat/send — SSE 流式入口
    │   ├── conversations.py         # CRUD 会话
    │   ├── outline.py               # GET 大纲（只读）
    │   ├── ppt.py                   # GET PPT + 下载（只读）
    │   ├── snapshot.py              # GET 快照（只读）
    │   ├── cost.py                  # 费用统计
    │   ├── knowledge.py             # 知识库文件上传/列表/删除
    │   ├── workspace.py             # 工作空间状态
    │   └── system.py                # GET /api/config + /api/health
    │
    ├── agent/                       # ═══ Agent 层 ═══
    │   ├── __init__.py
    │   ├── coordinator.py           # 意图分类 + 分发到 outline/ppt Agent
    │   │
    │   ├── outline/                 # 大纲生成
    │   │   ├── __init__.py
    │   │   ├── graph.py             # LangGraph: generator→evaluator→{continue|finalize}
    │   │   ├── state.py             # OutlineState TypedDict
    │   │   ├── generator.py         # create_agent: search_knowledge + search_web + fetch_web + write_outline
    │   │   ├── evaluator.py         # create_agent: submit_evaluation（评分+建议）
    │   │   ├── middleware.py         # TokenCountingMiddleware (after_model hook)
    │   │   └── prompts.py           # Evaluator rubric + user prompt builder
    │   │
    │   ├── ppt/                     # PPT 生成（两阶段流水线）
    │   │   ├── __init__.py
    │   │   ├── graph.py             # StateGraph: create_presentation → style_agent → supervisor* → assembly
    │   │   ├── state.py             # PPTState TypedDict
    │   │   ├── phase1_style.py      # Phase 1: StyleAgent（选配色+布局）
    │   │   │
    │   │   ├── phase2_sub_agent/    # Phase 2 模式 A — sub_agent
    │   │   │   ├── __init__.py
    │   │   │   ├── supervisor.py    # 逐页调度 TextAgent + ChartAgent + ShapeAgent（每页并发）
    │   │   │   ├── text_agent.py    # 文本框 + 表格 + SVG 图标
    │   │   │   ├── chart_agent.py   # 图表生成（读取 chart instruction + 提交 chart 元素）
    │   │   │   └── shape_agent.py   # 装饰形状（封面/章节/结尾页）
    │   │   │
    │   │   ├── phase2_freedom/      # Phase 2 模式 B — freedom
    │   │   │   ├── __init__.py
    │   │   │   ├── supervisor.py    # 逐页调度 FreedomAgent
    │   │   │   └── freedom_agent.py # 单 Agent 生成整页所有元素
    │   │   │
    │   │   ├── common/              # PPT Agent 共享模块
    │   │   │   ├── __init__.py
    │   │   │   ├── tools.py         # search_icons, read_instruction, submit_*_elements
    │   │   │   ├── instruction_loader.py  # 加载 JSON instruction 文件 + HOW_TO_READ.md
    │   │   │   └── layout_resolver.py     # 映射 layout_type→layout_name + 计算容器坐标
    │   │   │
    │   │   └── layout/              # 内置布局定义
    │   │       ├── __init__.py
    │   │       └── definitions.py   # 7 种布局 Python 常量（title_slide/section/content_bullet/...）
    │   │
    │   └── common/                  # Agent 全局共享
    │       ├── __init__.py
    │       └── langchain_adapter.py # DeepSeek V4 reasoning_content 适配补丁
    │
    ├── infrastructure/              # ═══ 基础设施层 ═══
    │   ├── config/
    │   │   ├── __init__.py
    │   │   ├── settings.py          # .env + config.yaml → 单例
    │   │   └── models.py            # Pydantic 配置模型
    │   │
    │   ├── rag/
    │   │   ├── __init__.py
    │   │   ├── bm25.py              # rank_bm25 + pickle 序列化
    │   │   ├── indexer.py           # BM25 分词 + 建索引
    │   │   ├── retriever.py         # top-k 检索
    │   │   ├── parser/              # 多格式文件解析
    │   │   │   ├── base.py          # ParsedDocument
    │   │   │   ├── docx_parser.py
    │   │   │   ├── pdf_parser.py
    │   │   │   ├── pptx_parser.py
    │   │   │   └── spreadsheet_parser.py  # 小表→Markdown / 大表→统计摘要
    │   │   ├── scraper.py           # 网页爬取 + BM25 索引
    │   │   └── store.py             # KnowledgeService: ingest/remove/search
    │   │
    │   ├── db/
    │   │   ├── __init__.py
    │   │   ├── engine.py            # SQLAlchemy async engine + create_all
    │   │   ├── models.py            # ORM 模型（11 张表）
    │   │   ├── database.py          # Database 门面，封装所有 CRUD
    │   │   └── repository/          # 每表 CRUD
    │   │       ├── user.py
    │   │       ├── conversation.py
    │   │       ├── knowledge.py
    │   │       ├── outline.py
    │   │       └── ppt.py
    │   │
    │   ├── ppt_engine/              # PPT 渲染引擎
    │   │   ├── __init__.py
    │   │   ├── generator.py         # SlideBuilder: JSON→python-pptx + cleanup_temp_icons
    │   │   ├── validator.py         # Instruction JSON 校验
    │   │   ├── parser/              # 指令解析器
    │   │   │   ├── base.py          # Element 数据模型（TextboxElement/TableElement/...）
    │   │   │   ├── image_parser.py  # 图片/SVG 渲染
    │   │   │   └── ...
    │   │   ├── icon_search.py       # Tabler 5,800+ 图标搜索 + SVG 上色
    │   │   ├── layouts.py           # 布局槽位定义
    │   │   ├── charts.py            # python-pptx 原生图表
    │   │   ├── images.py            # 图片嵌入 + cairosvg SVG→PNG
    │   │   ├── styles.py            # 颜色/字体/渐变/阴影
    │   │   └── tables.py            # 表格生成 + 边框/填充
    │   │
    │   ├── workspace/
    │   │   ├── __init__.py
    │   │   └── manager.py           # WorkspaceManager: get_input_dir/get_knowledge_dir/get_output_dir
    │   │
    │   └── utils/
    │       ├── __init__.py
    │       ├── token_counter.py     # Token 累加 + 费用估算
    │       └── logger.py            # 日志
    │
    └── resources/                   # ═══ 静态资源 ═══
        ├── prompts/                 # LLM Prompt 模板
        │   ├── coordinator_system.txt
        │   ├── outline/
        │   │   ├── generator_system.txt
        │   │   ├── evaluator_system.txt
        │   │   └── rubric.json
        │   └── ppt/
        │       └── style_agent_system.txt
        ├── instructions/            # PPT 元素 JSON Schema
        │   ├── HOW_TO_READ.md       # 指令文件阅读约定
        │   ├── textbox.json
        │   ├── table.json
        │   ├── picture.json         # SVG 图标元素
        │   ├── shape.json
        │   ├── background.json
        │   ├── shape_catalog.json   # 182 种可用形状
        │   ├── shared/              # position/font/fill/line 公共定义
        │   ├── chart/               # 8 种图表类型定义
        │   └── examples/            # 示例 JSON
        ├── layouts/                 # 7 种布局 JSON 定义
        │   ├── title_slide.json
        │   ├── section.json
        │   ├── content_bullet.json
        │   ├── content_two_column.json
        │   ├── content_three_column.json
        │   ├── content_grid_2x2.json
        │   └── ending.json
        ├── fonts/
        └── tabler/                  # Tabler Icons (5,800+ SVG)
│
└── tests/                           # ═══ 测试 ═══
    ├── __init__.py
    ├── conftest.py
    ├── test_api/
    ├── test_agent/
    ├── test_rag/
    │   └── test_spreadsheet_parser.py
    ├── test_ppt_engine/
    └── resources/                   # 测试用文件
```

---

## 四、Agent 层详解

### 4.1 Coordinator — 意图分类 + 分发

```
用户消息 → Coordinator._classify_intent()
              │  读取 conversation 状态（有无大纲、PPT）
              │  分析最近 10 条消息历史
              │  提取已上传的 image/file 上下文
              │
              ├── generate_outline / modify_outline → _run_outline()
              └── generate_ppt     / modify_ppt     → _run_ppt()
```

**关键行为：**
- 从消息历史中提取 `role="image"` 的图片路径 → 注入为 "可用图片素材"
- 从消息历史中提取 `role="file"` 的文件内容 → 注入为 "已上传文件内容"
- 分类后生成 `augmented_query = query + 图片路径 + 文件内容` 传给子 Agent
- 执行完成自动创建 `role="assistant"` 消息（含执行总结）

### 4.2 Outline Agent — Generator-Evaluator 循环

**StateGraph 流程：**

```
START → generator → evaluator → { continue? → generator, stop? → finalize } → END
```

**Generator node**（`create_agent`，4 个工具）：

| 工具 | 说明 |
|------|------|
| `search_knowledge` | BM25 搜索知识库 |
| `search_web` | DuckDuckGo 网页搜索 |
| `fetch_web` | 抓取单个 URL 并索引到知识库 |
| `write_outline` | **终止工具**，写入 DB 并返回 outline_id |

**Evaluator node**（`create_agent`，1 个工具）：

| 工具 | 说明 |
|------|------|
| `submit_evaluation` | **终止工具**，评分(0-10) + 修改建议 → 写入 DB |

**三种评估模式：**
- `max_iteration`：跑满 N 次后停止
- `pass_score`：评分 ≥ 阈值立即停止
- `mix`（默认）：满足任一条件即停止

**Finalize node**：从 DB 读取最终 outline + slides，打包发给前端。

### 4.3 PPT Agent — 两阶段流水线

**StateGraph 流程：**

```
START → create_presentation → { style_agent? }
                                  ↓
                              supervisor* → assembly → END
```

**Phase 1: StyleAgent**（`create_agent`，6 个工具）

| 工具 | 说明 |
|------|------|
| `list_color_schemes` | 列出 DB 中所有活跃配色 |
| `get_color_scheme` | 查看单个配色详情 |
| `save_color_scheme` | 新建配色方案 |
| `list_layouts` | 列出 7 种内置布局 |
| `get_layout` | 查看布局 JSON 定义 |
| `set_presentation_style` | **终止工具**，持久化选择到 presentation 表 |

**Phase 2: Supervisor（两种模式）**

| 模式 | 配置 key | 说明 |
|------|---------|------|
| sub_agent | `agent.ppt.mode = "sub_agent"` | 每页并发调度 TextAgent + ChartAgent + ShapeAgent |
| freedom | `agent.ppt.mode = "freedom"` | 单 FreedomAgent 生成整页所有元素 |

**Sub-agent 分发逻辑**（每页，agents 并发执行）：

| Agent | 触发条件 | 产出 |
|-------|---------|------|
| TextAgent | 总是 | textbox / table / picture (SVG icon) 元素 |
| ChartAgent | `has_chart == true` | chart 元素（18 种图表类型） |
| ShapeAgent | `layout_type` 为 title/section/ending | 装饰 shape 元素 |

**共同的工具模式：** 每个 agent 通过 `read_instruction()` 读取对应的 JSON Schema，生成元素后通过 `submit_*_elements()` 提交（经 Pydantic validator 校验）。

**Assembly node**：标记 presentation 状态为 completed。

### 4.4 Token 计数

通过 `TokenCountingMiddleware`（LangChain `AgentMiddleware`）的 `after_model` hook 自动累加：

```
每次 LLM 调用 → after_model() → TokenCounter.for_conversation(id).add(usage_metadata)
```

无需手动调用，所有 `create_agent` 均注入此 middleware。

### 4.5 DeepSeek V4 适配补丁

`agent/common/langchain_adapter.py` 修复 LangChain 与 DeepSeek V4 Thinking Mode 的兼容问题：

1. `_create_chat_result` patch：从 OpenAI SDK 响应中提取 `reasoning_content` → 存入 AIMessage.additional_kwargs
2. `_convert_message_to_dict` patch：多轮 Tool Calling 时将 `reasoning_content` 原样传回 API

在所有 `create_agent` / `build_*_graph` 前调用 `apply_deepseek_patch()`。

---

## 五、PPT 生成数据流

```
Outline slide (content_json)
    │
    ├── Phase 1: StyleAgent
    │       选择 color_scheme + layout → presentation 表
    │
    ├── Phase 2: Per-Slide
    │   ├── TextAgent → textbox/table/picture elements → agent_outputs["text"]
    │   ├── ChartAgent → chart element → agent_outputs["chart"]
    │   └── ShapeAgent → shape elements → agent_outputs["shape"]
    │
    └── Assembly
         validator 校验 → python-pptx 渲染 → output.pptx
```

**指令系统**：`resources/instructions/*.json` 定义每种元素的 JSON Schema。Agent 通过 `read_instruction("textbox.json")` 等工具读取。`HOW_TO_READ.md` 说明类型约定（`string|null`、`hex[]` 等）。

---

## 六、BM25 索引持久化

按 user 全局索引（跨 conversation 共享检索）：

```
data/workspace/indexes/bm25_index_{user_id}.pkl
```

文件上传时自动重建索引。对 PPT 场景（<100 文件、<10MB 文本），重建 <200ms。

---

## 七、Layout 布局体系

**7 种内置布局**（`resources/layouts/*.json` + `agent/ppt/layout/definitions.py` 常量）：

| 布局 | 适用场景 |
|------|---------|
| title_slide | 封面 |
| section | 章节分隔页 |
| content_bullet | 标题+正文（默认） |
| content_two_column | 双栏对比 |
| content_three_column | 三栏 |
| content_grid_2x2 | 2×2 四象限 |
| ending | 结尾/致谢 |

**布局选择逻辑**（`layout_resolver.select_layout()`）：

```
outline_slide.layout_type → LAYOUT_MAP
    "title"   → title_slide
    "section" → section
    "content" → 检查 content_json.recommended_ppt_format
                  "two_column"   → content_two_column
                  "four_grid"    → content_grid_2x2
                  default        → content_bullet
```

---

## 八、配置

### config.yaml
```yaml
workspace:
  root: "./data/workspace"

rag:
  algorithm: "bm25"
  top_k: 5
  bm25_index_file: "bm25_index.pkl"
  supported_formats: [".txt", ".pdf", ".docx", ".csv", ".xlsx", ".pptx", ".md"]

agent:
  outline:
    max_iterations: 5
    pass_score: 7.0
    mode: "mix"              # max_iteration | pass_score | mix
  ppt:
    mode: "sub_agent"        # sub_agent | freedom
  cache:
    trim_max_tokens: 20000
    enable_node_cache: true

llm:
  provider: "deepseek"
  base_url: "https://api.deepseek.com/v1"
  api_key: "your_api_key"
  model: "deepseek-v4-flash"
  temperature: 0.7
  max_tokens: 50000

db:
  type: "mysql"
  url: "mysql+asyncmy://{username}:{password}@localhost:3306/pptgenius"

web_search:
  enabled: true
  engine: "duckduckgo"
  max_results: 5
```

### .env
```env
API_BASE_URL=https://api.deepseek.com
API_KEY=sk-xxx
API_MODEL=deepseek-v4-flash
PYTHONUTF8=1
```

---

## 九、Benchmark

单文件 `src/benchmark.py`，评估已积累的 Outline/Presentation 数据：

| 维度 | 说明 |
|------|------|
| Token 开销 | 按 Outline-only / PPT 会话分类统计 `message.estimated_cost` |
| Outline 分数 | `outlines.eval_score` 均值/标准差/最值 |
| Traceability | Outline 每句 → BM25 搜索知识库，统计可追溯句子占比 |

输出 HTML 报告到 `docs/benchmark_report.html`，含 matplotlib 图表。
