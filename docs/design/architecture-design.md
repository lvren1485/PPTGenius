# PPTGenius 架构设计

> BM25 检索 + LangGraph Agent + FastAPI 单人网站
> 日期：2026-06-03 · 最后更新：python-pptx 调研后修订

---

## 一、技术选型

| 层面 | 选择 | 理由 |
|------|------|------|
| 语言 | Python 3.12+ | uv 管理 |
| Web 框架 | FastAPI | 异步支持好，自动生成 API 文档 |
| Agent 框架 | LangGraph（库方式） | generator-evaluator 循环 + supervisor-subagent |
| RAG 检索 | BM25（rank_bm25） | 文件量不大，无需向量库 |
| BM25 持久化 | pickle 序列化 | 启动时加载，免重建 |
| 数据库 | MySQL + asyncmy | SQLAlchemy async engine，部署用 |
| 配置 | .env + config.yaml | 密钥 env，业务 yaml |
| LLM | DeepSeek API | 已适配 v4，OpenAI 兼容 SDK |
| PPT 引擎 | python-pptx | 成熟稳定，原生图表/表格/形状 |
| 图表 | python-pptx 原生图表 | 非 matplotlib→PNG，原生图表可编辑+矢量 |
| SVG 处理 | cairosvg → PNG | python-pptx 不支持 SVG，300 DPI 转换 |
| 文件解析 | python-docx, PyPDF2, openpyxl | docx/pdf/txt/csv/xlsx |
| 网络爬取 | httpx + BeautifulSoup | |
| 包管理 | uv | |

### 为什么不用 langgraph dev/deploy

- `langgraph dev` 需要 Docker + Redis + Postgres，单人网站过重
- 只把 LangGraph 当库用，部署就是 `uv run python main.py`
- 数据库用 SQLite，不需要 Postgres

---

## 二、整体架构

```
浏览器 ──HTTP/SSE──► FastAPI (src/pptgenius/main.py:app)
                          │
         ┌────────────────┼────────────────┐
         │                │                │
    ┌─ api/ ─┐    ┌─ agent/ ─┐    ┌─ infrastructure/ ─┐
    │ routes │    │ outline  │    │ config  │ rag(BM25)│
    │ deps   │    │ ppt      │    │ db      │ ppt_engine│
    │ SSE    │    │ common   │    │workspace│ utils     │
    └────────┘    └──────────┘    └────────────────────┘
         │                │                │
         └────────────────┼────────────────┘
                          │
              ┌─ resources/ ─┐  ┌─ tests/ ────────────┐
              │ prompts/     │  │ test_api/            │
              │ fonts/       │  │ test_agent/          │
              └──────────────┘  │ test_rag/            │
                                │ test_ppt_engine/     │
                                │ benchmark/           │
                                │  ├ test_quality      │
                                │  ├ test_traceability │
                                │  └ test_timing       │
                                └──────────────────────┘
```

三层依赖：api → agent → infrastructure。（infrastructure 不依赖上层）

---

## 三、文件结构

```
backend/
├── main.py                          # 薄启动器: from pptgenius.main import main
├── pyproject.toml                   # 项目元数据 + 依赖
├── uv.lock
├── .env                             # API_KEY, BASE_URL, MODEL
├── config.yaml                      # 业务配置
│
└── src/pptgenius/
    ├── __init__.py                  # __version__
    ├── main.py                      # FastAPI app = create_app() + uvicorn 启动
    │
    ├── api/                         # ═══════ Web API 层 ═══════
    │   ├── __init__.py
    │   ├── router.py                # 注册所有子路由
    │   ├── deps.py                  # Depends: Settings, DB session, Agent
    │   ├── chat.py                  # POST /api/chat/send — SSE 流式
    │   ├── outline.py               # POST 生成 / PUT 用户反馈(message)
    │   ├── ppt.py                   # POST 生成 / GET 下载 / PUT 修改(message)
    │   ├── knowledge.py             # CRUD 知识库
    │   └── workspace.py             # 工作空间状态 / 清理
    │
    ├── agent/                       # ═══════ Agent 层 ═══════
    │   ├── __init__.py
    │   │
    │   ├── outline/                 # 大纲生成
    │   │   ├── __init__.py
    │   │   ├── graph.py             # LangGraph StateGraph
    │   │   ├── generator.py         # LLM + BM25 检索 → 大纲
    │   │   ├── evaluator.py         # 评分 + 修改建议
    │   │   └── prompts.py
    │   │
    │   ├── ppt/                     # PPT 生成
    │   │   ├── __init__.py
    │   │   ├── graph.py             # supervisor-subagent
    │   │   ├── supervisor.py        # 主协调器
    │   │   ├── text_agent.py        # 文本内容
    │   │   ├── image_agent.py       # 图片爬取/嵌入
    │   │   ├── chart_agent.py       # [待做] 图表
    │   │   ├── layout_agent.py      # 布局 + 配色 (每次动态生成)
    │   │   └── prompts.py
    │   │
    │   └── common/                  # Agent 共享
    │       ├── __init__.py
    │       ├── state.py             # State TypedDict
    │       ├── llm.py               # LLM 客户端 (封装 token 计数)
    │       └── cache_mgr.py         # trim_messages + 缓存策略
    │
    ├── infrastructure/              # ═══════ 基础设施层 ═══════
    │   ├── __init__.py
    │   │
    │   ├── config/                  # 配置
    │   │   ├── __init__.py
    │   │   ├── settings.py          # 加载 .env + config.yaml
    │   │   └── models.py            # Pydantic 配置模型
    │   │
    │   ├── rag/                     # BM25 RAG
    │   │   ├── __init__.py
    │   │   ├── bm25.py              # rank_bm25 封装 + pickle 保存/加载
    │   │   ├── indexer.py           # 分词 + 建索引
    │   │   ├── retriever.py         # 检索 top-k
    │   │   ├── parser.py            # 多格式文件解析
    │   │   ├── scraper.py           # 网页爬取
    │   │   └── store.py             # 知识文件管理
    │   │
    │   ├── db/                      # 数据库
    │   │   ├── __init__.py
    │   │   ├── engine.py            # SQLAlchemy 连接 (create_all 自动建表)
    │   │   ├── models.py            # ORM 模型
    |   |   ├── database.py          # DB 薄封装，repository不需要传入 session
    │   │   └── repository/          # CRUD
    │   │       ├── __init__.py
    │   │       ├── user.py
    │   │       ├── conversation.py
    │   │       ├── knowledge.py
    │   │       ├── outline.py
    │   │       └── ppt.py
    │   │
    │   ├── ppt_engine/              # PPT 引擎
    │   │   ├── __init__.py
    │   │   ├── generator.py         # SlideBuilder: JSON→python-pptx 组装
    │   │   ├── parser.py            # InstructionParser: JSON Schema 校验
    │   │   ├── layouts.py           # N 种布局槽位定义 + 模板管理
    │   │   ├── charts.py            # python-pptx 原生图表生成
    │   │   ├── images.py            # 图片嵌入 + SVG→PNG 转换
    │   │   └── styles.py            # 颜色/字体/渐变/阴影工具函数
    │   │   ├── tables.py            # 表格生成 + 边框/填充
    │   │
    │   ├── workspace/               # 工作空间
    │   │   ├── __init__.py
    │   │   ├── manager.py           # 创建/清理
    │   │   └── state.py             # 状态追踪
    │   │
    │   └── utils/                   # 工具
    │       ├── __init__.py
    │       ├── token_counter.py     # Token 累加 + 费用估算 (由 llm.py / LangGraph node 调用)
    │       └── logger.py            # 日志
    │
    └── resources/                   # ═══════ 静态资源 ═══════
        ├── __init__.py
        ├── prompts/                 # LLM Prompt 模板 (.md)
        │   ├── outline_generator.md
        │   ├── outline_evaluator.md
        │   ├── ppt_supervisor.md
        │   ├── ppt_text.md
        │   ├── ppt_image.md
        │   ├── ppt_chart.md
        │   └── ppt_layout.md
        ├── fonts/                   # 自定义字体(可选)
        └── templates/               # 模板 & 配色 JSON
            ├── index.json           # 模板索引
            ├── color_schemes/       # 配色方案
            │   ├── business_blue.json
            │   ├── academic_warm.json
            │   ├── minimal_dark.json
            │   └── creative_vivid.json
            └── layouts/             # 布局定义
                ├── title_slide.json
                ├── content_bullet.json
                ├── content_chart.json
                ├── content_table.json
                ├── two_column.json
                ├── image_text.json
                └── ending.json
│
└── tests/                           # ═══════ 测试 (与 pptgenius 并列) ═══════
    ├── __init__.py
    ├── conftest.py                  # pytest fixtures
    ├── test_api/                    # API 集成测试
    ├── test_agent/                  # Agent 图测试
    ├── test_rag/                    # BM25 + 文件解析测试
    ├── test_ppt_engine/             # PPT 生成测试
    └── benchmark/                   # 基准评测
        ├── __init__.py
        ├── test_quality.py          # LLM+evaluator 质量评分
        ├── test_traceability.py     # BM25 知识溯源率
        └── test_timing.py           # 3轮计时基准
```

**目录变更说明：**

| 变更 | 理由 |
|------|------|
| `resources/` 迁入 `src/pptgenius/` | 作为包的静态资源，不应放在包外 |
| `tests/` 迁入 `src/tests/` | 与 pptgenius 并列于 src 下，`pytest src/tests/` 运行 |
| `main.py` 迁到 `src/pptgenius/main.py` | FastAPI app 紧邻 api/ 模块，减少跨层引用 |
| 根 `main.py` 变为薄启动器 | 只做 `from pptgenius.main import main` |
| 删除 `db/migrations/` | SQLite 单人场景 `create_all()` 足够 |
| 新增 `tests/benchmark/` | 三个基准评测 |
| `ppt_engine/` 增加 parser.py, tables.py | 调研发现需 JSON 解析层 + 表格工具函数 |
| `resources/` 增加 templates/ | JSON 模板 + 配色方案，seed 后入库 |
| `charts.py` 改为原生图表 | python-pptx 原生图表优于 matplotlib→PNG |

---

## 四、各模块职责

### 4.1 api/ — Web API 层

薄层。只做参数校验、SSE 封装、调用 agent、返回结果。不写业务逻辑。

| 文件 | 职责 |
|------|------|
| `main.py` | `create_app()` + `uvicorn.run()`，FastAPI app 定义 |
| `router.py` | 注册全部子路由 |
| `deps.py` | FastAPI `Depends()` — 注入 Settings、DB session、Agent 实例 |
| `chat.py` | SSE 流式 — 接收 message → 调 agent → 转发进度事件 |
| `outline.py` | POST 生成大纲 + PUT 用户反馈 (仅 message) |
| `ppt.py` | POST 生成 + GET 下载 + PUT 修改 (仅 message) |
| `knowledge.py` | 知识库文件 CRUD |
| `workspace.py` | 工作空间状态 / 清理 |

### 4.2 agent/ — Agent 层

核心业务。所有 LangGraph StateGraph 定义和节点实现。

**outline/ — 大纲生成**
| 文件 | 职责 |
|------|------|
| `graph.py` | 三循环 StateGraph: ①Gen↔知识库 ②Gen↔Evaluator ③体系↔用户 |
| `generator.py` | LLM + BM25 检索 → 结构化大纲 |
| `evaluator.py` | 评估完整性/逻辑/专业性 → 评分 + 建议 |
| `prompts.py` | Prompt 模板 |

**ppt/ — PPT 生成**
| 文件 | 职责 |
|------|------|
| `graph.py` | supervisor-subagent StateGraph |
| `supervisor.py` | 逐页决定调用哪些子 agent |
| `text_agent.py` | 文本内容填充 |
| `image_agent.py` | 图片爬取/嵌入 |
| `chart_agent.py` | 数据分析 → 选择图表类型 → 生成 python-pptx 原生图表 |
| `table_agent.py` | [新增] 表格数据组织 → 单元格内容 + 合并 + 样式 |
| `layout_agent.py` | 从模板 JSON 池选择 layout + 配色方案，计算元素坐标 |
| `layout_generator.py` | [新增] 根据 layout 定义 + agent 输出 → 生成 PPTInstruction JSON |
| `prompts.py` | 各 sub-agent 的 Prompt 模板（含 JSON Schema 约束） |

**common/ — Agent 共享**
| 文件 | 职责 |
|------|------|
| `state.py` | LangGraph State (TypedDict) |
| `llm.py` | DeepSeek v4 适配 + 封装 `token_counter`，每次调用自动记录 token |
| `cache_mgr.py` | 上下文裁剪：`trim_messages` + 消息窗口控制 |

### 4.3 infrastructure/ — 基础设施层

为 agent 和 api 提供底层能力，不依赖上层。

| 模块 | 关键文件 | 职责 |
|------|---------|------|
| config | `settings.py` | 加载 .env + config.yaml → 单例 |
| rag | `bm25.py` | BM25 + pickle 持久化 |
| rag | `indexer.py` | 分词 + 建索引 |
| rag | `retriever.py` | top-k 检索 |
| rag | `parser.py` | 多格式文件解析 |
| rag | `scraper.py` | 网页爬取 |
| rag | `store.py` | 知识文件存储 + DB 元数据 |
| db | `engine.py` | SQLAlchemy async engine: `create_async_engine("mysql+asyncmy://...")`，`create_all` 启动时自动建表 |
| db | `models.py` | ORM 模型 |
| db | `repository/` | 每表 CRUD |
| ppt_engine | `generator.py` | SlideBuilder: 接收 PPTInstruction JSON，组装 python-pptx |
| ppt_engine | `parser.py` | [新增] InstructionParser: Pydantic 校验 + JSON→内部模型 |
| ppt_engine | `layouts.py` | N 种布局槽位定义 + 坐标计算引擎 |
| ppt_engine | `charts.py` | python-pptx 原生图表：柱/线/饼/散点/气泡 |
| ppt_engine | `tables.py` | [新增] 表格生成 + lxml 边框/填充 |
| ppt_engine | `images.py` | 图片嵌入/缩放 + cairosvg SVG→PNG |
| ppt_engine | `styles.py` | 颜色/字体/渐变/阴影工具函数 |
| workspace | `manager.py` | 目录创建/清理 |
| utils | `token_counter.py` | Token 累加 + 费用估算，**由 llm.py / LangGraph callback 自动调用** |
| utils | `logger.py` | 日志 |

### Token 计数调用链

```
api/chat.py
  → agent/common/llm.py.chat_completion()
      → 调用前: token_counter.count(messages)
      → 调用后: token_counter.count(response)
      → 自动累加到 conversation.estimated_cost
```

外部模块不需要手动调用 `token_counter`，llm.py 内部封装。

---

## 五、BM25 索引持久化

`rank_bm25` 的 BM25Okapi 索引结构可通过 `pickle` 直接序列化：

```python
# infrastructure/rag/bm25.py
class BM25Manager:
    def save(self, path: str) -> None:
        with open(path, "wb") as f:
            pickle.dump(self._index, f)

    def load(self, path: str) -> bool:
        if not os.path.exists(path): return False
        with open(path, "rb") as f:
            self._index = pickle.load(f)
        return True
```

每个 conversation 的 workspace 独立存储 BM25 索引：

```
data/workspace/{conversation_id}/bm25_index.pkl
```

不同用户（user_id）的不同会话（conversation_id）各自隔离，不会冲突。对 PPT 场景（<100 文件、<10MB 文本），索引构建 <200ms，新增文件直接重建。

---

## 六、上下文缓存策略

LangGraph 中 `ToolMessage` 通过 `add_messages` reducer 追加到 messages 列表，每次工具调用占用上下文。

### 三个策略

**1. 消息裁剪**
```python
# agent/common/cache_mgr.py
trim_messages(messages, strategy="last", max_tokens=8000,
              start_on="human", end_on=("human", "tool"))
```

**2. 状态分离** — 工具结果放独立 state 字段，不污染 messages：
```python
class OutlineState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]  # 精简对话
    rag_results: list[str]     # BM25 结果放独立字段
    eval_report: dict          # Evaluator 报告放独立字段
```

**3. 图拆分** — Outline Agent 和 PPT Agent 为两个独立 StateGraph：
- 中间以 FastAPI 层为桥梁
- Outline 结束 → checkpoint → 释放上下文
- PPT 启动 → 只接收 outline_json + 确认 message（精简上下文）
- 两个 Agent 不共享 messages 历史，各自缓存命中更高

---

## 七、PPT 模板与 Agent Checkpoint 策略

### 7.1 模板策略：JSON 模板 + DB 存储

不使用 .pptx 模板文件（python-pptx 不能通过 API 创建自定义 slide layout），改用 JSON 定义。

**三层模板体系**：

```
resources/templates/
├── index.json              # 模板索引
├── color_schemes/          # 4 套配色方案
│   ├── business_blue.json  #   { colors, chart_colors, fonts }
│   ├── academic_warm.json
│   ├── minimal_dark.json
│   └── creative_vivid.json
└── layouts/                # 7 种布局定义
    ├── title_slide.json    #   { name, label, placeholders[] }
    ├── content_bullet.json
    ├── content_chart.json
    ├── content_table.json
    ├── two_column.json
    ├── image_text.json
    └── ending.json
```

- **seed 脚本**在首次部署时将 JSON 导入 `templates` 和 `color_schemes` 表
- `layout_agent` 从 DB 读取可用模板 → **选择**而非发明配色/布局
- 每页可选择不同的 layout（如第3页用 content_chart，第4页用 content_table）
- 坐标/尺寸从 JSON 的 placeholders 中读取，保证一致性

### 7.2 生成流程：Sub-Agent 独立 Checkpoint

```
supervisor 逐页调度 sub-agent：

  第 k 页开始:
    layout_agent → 选择 template + color_scheme + layout → 写入 presentation_slides[k]
    text_agent   → 产出 text elements → agent_outputs["text"] = [...] → status=text_done
    chart_agent  → 产出 chart_data + chart element → status=chart_done
    table_agent  → 产出 table_data + table element → status=table_done
    image_agent  → 图片下载+嵌入 → agent_outputs["image"] = {...} → status=completed

  失败处理:
    任意 agent 失败 → status=failed + error_message + retry_count++
    supervisor 重试时检查 agent_outputs → 只调失败的 agent
    重试上限 3 次，超限则标记为 failed 并告知用户
```

**关键设计**：每个 agent 产出独立写入 `agent_outputs` 字段。text_agent 成功后的数据不会因为 chart_agent 超时而丢失。

### 7.3 python-pptx 渲染管线

```
PPTInstruction JSON (LLM 产出, 经 Pydantic 校验)
  │
  ▼
Parser (parser.py):       JSON → Slid`Spec[] → 校验字段完整性
  │
  ▼
SlideBuilder (generator.py):  逐页 逐元素渲染
  ├── textbox  → add_textbox() + apply_font()
  ├── chart    → CategoryChartData → add_chart() + apply_chart_style()
  ├── table    → add_table() + fill cells + apply borders (lxml)
  ├── picture  → add_picture() (SVG 先 cairosvg→PNG)
  └── shape    → add_shape() + fill/line/gradient
  │
  ▼
output.pptx
```

---

## 八、Benchmark 评测体系

位于 `tests/benchmark/`。每次重大改动后运行，结果记录到 `data/benchmark/`。

### 8.1 test_quality.py — LLM 质量评分

复用 `agent/outline/evaluator.py` 对生成结果打分：

- 选取 3 个不同领域主题（科技/教育/商务）
- 每个主题生成大纲 → evaluator 评分
- 输出：各主题评分、均值、evaluator 建议列表
- 评分维度：完整性、逻辑性、专业性、美观性

### 8.2 test_traceability.py — BM25 知识溯源

测量生成内容中有多少可追溯到知识库：

- 预置测试知识库文件（含已知事实）
- 生成大纲 → 提取关键断言
- BM25 检索验证每个断言是否在知识库中有支撑
- 输出：溯源率（有支撑的断言/总断言）

### 8.3 test_timing.py — 计时基准

端到端计时，连续 3 轮：

- 固定输入（相同 topic + 相同知识库）
- 记录：每轮总耗时、各阶段耗时（RAG / Outline / PPT / 总计）
- 输出：min / max / mean / p50

```
示例输出:
  RAG indexing:  mean=0.15s  min=0.12s  max=0.18s
  Outline gen:   mean=28.3s  min=25.1s  max=32.0s
  PPT gen:       mean=12.5s  min=10.2s  max=14.8s
  Total:         mean=41.0s  min=35.5s  max=47.0s
```

---

## 九、配置

### config.yaml
```yaml
workspace:
  root: "./data/workspace"

rag:
  algorithm: "bm25"
  top_k: 5
  bm25_index_file: "bm25_index.pkl"       # 文件名模板，实际路径: workspace/{conv_id}/bm25_index.pkl
  supported_formats: [".txt", ".pdf", ".docx", ".csv", ".xlsx"]

agent:
  outline:
    max_iterations: 5
    evaluation_threshold: 0.7
  cache:
    trim_max_tokens: 8000

llm:
  provider: "deepseek"
  base_url: "https://api.deepseek.com/v1"
  api_key: "your_deepseek_api_key"
  model: "deepseek-v4-flash"
  temperature: 0.7
  max_tokens: 50000

db:
  type: "mysql"
  url: "mysql+asyncmy://{username}:{password}@localhost:3306/pptgenius"
```

### .env
```env
API_BASE_URL=https://api.deepseek.com
API_KEY=sk-xxx
API_MODEL=deepseek-v4-flash
PYTHONUTF8=1
```

---

## 十、数据库

### 10.1 新增表

基于 python-pptx 调研结论，新增 `templates` 和 `color_schemes` 两张表存储模板数据，详见 [database-design.md](database-design.md)。

### 10.3 presentation_slides 设计意图

| 设计点 | 说明 |
|--------|------|
| `agent_outputs` JSON | 每个 sub-agent 独立写入产出。text_agent 成功后即使 chart_agent 超时，text 数据不丢失 |
| `chart_data` / `table_data` | LLM 产出的纯数据，与 element JSON 解耦。供重试时读取和修改 |
| `status` 细粒度 | `pending → text_done → chart_done → table_done → completed`。supervisor 按状态跳过已完成的 agent |
| `outline_slide_id` | outline_slide : presentation_slide = 1:1，可追溯 |
| `error_message` + `retry_count` | 失败信息 + 重试上限（3 次） |

### 10.4 完整 ER 图（新增部分）

```
┌──────────────────────┐       ┌──────────────────────┐
│      templates       │       │    color_schemes     │
│──────────────────────│       │──────────────────────│
│ PK id                │       │ PK id                │
│    name (unique)     │       │    name (unique)     │
│    label             │       │    label             │
│    category          │       │    colors_json       │
│    layouts_json      │       │    chart_colors_json │
│    slide_width/h     │       │    fonts_json        │
│    is_active         │       │    is_active         │
└──────┬───────────────┘       └──────────┬───────────┘
       │ FK                              │ FK
       ▼                                 ▼
┌───────────────────┐          ┌──────────────────────────┐
│  presentations    │ 1:N      │   presentation_slides    │
│──────────────────│──────────│──────────────────────────│
│ PK id             │          │ PK id                    │
│ FK conversation   │          │ FK presentation_id       │
│ FK outline        │          │ FK outline_slide_id      │
│ FK template ──────┘          │ FK template_id           │
│ FK color_scheme ─┘           │ FK color_scheme_id       │
│    file_path       │         │    slide_index           │
│    slide_count     │         │    layout_name           │
│    status          │         │    agent_outputs (JSON)  │
└───────────────────┘         │    chart_data (JSON)      │
                               │    table_data (JSON)      │
                               │    image_paths (JSON)     │
                               │    status                 │
                               │    error_message          │
                               │    retry_count            │
                               └──────────────────────────┘
```

### 10.5 数据初始化

`resources/templates/` 下的 JSON 文件在首次部署时通过 seed 脚本导入：

```python
# infrastructure/db/seed.py — 首次部署时运行
async def seed(engine):
    import json, glob
    async with engine.begin() as conn:
        for f in glob.glob("resources/templates/color_schemes/*.json"):
            d = json.load(open(f, encoding="utf-8"))
            await conn.execute(insert(ColorScheme).values(
                name=d["name"], label=d["label"],
                colors_json=d["colors"], chart_colors_json=d["chart_colors"],
                fonts_json=d["fonts"]))
        for f in glob.glob("resources/templates/layouts/*.json"):
            d = json.load(open(f, encoding="utf-8"))
            # layouts 合并到一个 template 的 layouts_json 中
        await conn.execute(insert(Template).values(
            name="default", label="默认模板",
            layouts_json=[...所有 layout...]))
