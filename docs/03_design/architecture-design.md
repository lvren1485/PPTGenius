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
    │   │   ├── graph.py             # StateGraph: create_presentation → style_agent → dispatcher → assembly
    │   │   ├── state.py             # PPTState TypedDict
    │   │   ├── dispatcher.py        # Phase 2 Dispatcher: 多轮重试 + 并发调度 + SSE 事件推送
    │   │   ├── phase1_style.py      # Phase 1: StyleAgent（选配色+布局）
    │   │   │
    │   │   ├── phase2_sub_agent/    # Phase 2 模式 A — sub_agent [已废弃]
    │   │   │   ├── __init__.py
    │   │   │   ├── supervisor.py    # 逐页调度 TextAgent + ChartAgent + ShapeAgent（每页并发）
    │   │   │   ├── text_agent.py    # 文本框 + 表格 + SVG 图标
    │   │   │   ├── chart_agent.py   # 图表生成（读取 chart instruction + 提交 chart 元素）
    │   │   │   └── shape_agent.py   # 装饰形状（封面/章节/结尾页）
    │   │   │
    │   │   ├── phase2_freedom/      # Phase 2 模式 B — freedom [已废弃]
    │   │   │   ├── __init__.py
    │   │   │   ├── supervisor.py    # 逐页调度 FreedomAgent
    │   │   │   └── freedom_agent.py # 单 Agent 生成整页所有元素
    │   │   │
    │   │   ├── phase2_super_freedom/ # Phase 2 模式 C — super_freedom [当前使用]
    │   │   │   ├── __init__.py
    │   │   │   ├── agent.py         # SuperFreedomAgent: 完全创作自由
    │   │   │   └── prompts.py       # system/user prompt 构建（注入配色/模板/邻居上下文）
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
        │       ├── style_agent_system.txt
        │       ├── super_freedom_system.txt
        │       └── super_freedom_user.txt
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
                              dispatcher → assembly → END
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

`style_agent_node` 有重试机制：若 `set_presentation_style` 未被调用，以 stripped-down agent 重试（仅有 `set_presentation_style` 一个工具）。若已有 color_scheme_id + template_id（如 modify 模式），`_route_style` 直接跳过 Phase 1。

**Phase 2: Dispatcher（多轮重试并发调度）**

Dispatcher 为纯代码节点（无 LLM），负责：
1. `_create_presentation_node` 预先创建所有 presentation_slides（batch insert），解决 "先有鸡还是先有蛋" 问题
2. 以 `asyncio.gather` 并发处理所有 slides（通过 semaphore 控制并发数 `_MAX_CONCURRENT_SLIDES`）
3. 每轮结束后收集失败 slides，进入下一轮重试（最多 `_MAX_RETRY_ROUNDS=3` 轮）
4. 每 slide 获取独立 DB session（通过 `SessionManager.new_session()`），避免并发写入冲突
5. 通过 `asyncio.Queue` + `get_stream_writer()` 实时 SSE 推送进度事件（`slide_start` / `slide_end`）
6. 每 slide 构建相邻页上下文 `_build_neighbor_context()`（前后各 2 页的标题 + layout_type）

**Phase 2 三条管线对比：**

| 管线 | 配置 key | 状态 | 核心思路 |
|------|---------|------|---------|
| sub_agent | `agent.ppt.mode = "sub_agent"` | **已废弃** | 每页 3 Agent 并发（Text+Chart+Shape），各负责一类元素 |
| freedom | `agent.ppt.mode = "freedom"` | **已废弃** | 每页 1 Agent 生成全部元素 |
| super_freedom | `agent.ppt.mode = "super_freedom"` | **当前使用** | 每页 1 Agent，完全创作自由，模板仅供参考 |

**管线 A — sub_agent**（`phase2_sub_agent/`）

每页并发运行 3 个独立 Agent：

| Agent | 触发条件 | 工具 | 产出 |
|-------|---------|------|------|
| TextAgent | 总是 | `search_icons`, `read_instruction`, `submit_text_elements` | textbox / table / picture (SVG icon) 元素 |
| ChartAgent | `has_chart == true` | `read_chart_instruction`, `submit_chart_element` | chart 元素（8 种图表类型：column_clustered, line, pie, doughnut, bar_clustered, area, radar, scatter） |
| ShapeAgent | `layout_type` 为 title/section/ending | `submit_shape_elements` | 装饰 shape 元素（几何图形、圆形、六边形等） |

每个 Agent 通过 `read_instruction()` 读取 JSON Schema，通过 `submit_*_elements()` 提交经 Pydantic validator 校验的元素。三个 Agent 的结果存入 `agent_outputs["text"]`、`agent_outputs["chart"]`、`agent_outputs["shape"]`。

**管线 B — freedom**（`phase2_freedom/`）

每页单个 FreedomAgent，一次调用生成整页所有元素（textbox/table/chart/shape/picture）。工具：`search_icons`, `read_instruction`, `submit_slide_elements`（终止工具）。temperature=0.3, max_tokens=16000。Supervisor 逐页串行处理（非并发）。

**管线 C — super_freedom**（`phase2_super_freedom/`，当前激活）

每页单个 SuperFreedomAgent，完全创作自由——模板和布局仅供参考，Agent 自行决定所有元素的位置、大小、样式。工具链：
- `search_icons`：搜索 Tabler 5,800+ SVG 图标库
- `read_instruction`：读取 JSON Schema 定义
- `submit_slide_instruction`：**终止工具**，一次性提交 background + elements + notes

关键设计：
- `recursion_limit=50`（高于默认 25，适应多工具调用的 slide 设计循环）
- **重试机制**：若 `submit_slide_instruction` 未被调用，启动 stripped-down retry agent（仅含 submit 工具，System Prompt 强制直接提交），解决 DeepSeek thinking mode 不支持 `tool_choice` 的问题
- **Prompt 注入**：系统提示注入全部 6 种元素的 JSON Schema（textbox/table/picture/shape/background/chart）+ 设计规范（字体≥14pt、4 色调色板、6-15 元素/slide）+ 完整 title_slide 示例
- **User Prompt**：注入 slide 内容（title/layout_type/main_points/detailed_content/key_data）、配色方案（primary/accent/text/bg/chart_colors/fonts）、模板参考（layout 定义）、相邻页上下文（前后各 2 页）

**Assembly node**（`_assembly_node`）：
1. 从 DB 读取所有 presentation_slides，提取 `agent_outputs["super_freedom"]`
2. 构建 instruction JSON（meta + slides 数组，每 slide 含 layout/background/notes/elements）
3. 调用 `generate_ppt()` → python-pptx 渲染 → 输出 `{pres_id}.pptx`
4. 创建 snapshot（outline_json + presentation_json）写入 DB
5. 更新 presentation 状态为 completed

### 4.3.1 三条管线方案评价

**sub_agent 方案的问题：**

三个 Agent（TextAgent / ChartAgent / ShapeAgent）独立并发执行，各自只能看到自己的 instruction，**无法感知其他 Agent 生成的元素位置**。例如 ShapeAgent 在左上角放了一个装饰圆，TextAgent 同时在左上角放了标题文本框——两者重叠，最终渲染时元素堆叠混乱。此外，三个 Agent 各自拿到了整个 slide 的可用空间，没有 "已占用区域" 的概念，导致元素密度不可控。

**freedom 方案的问题：**

单 Agent 生成整页避免了元素重叠，但 Agent 被限制在 layout 定义的固定容器内放置元素。**Agent 无法修改或扩展 layout 本身**——如果 layout 只定义了标题区和正文区，整页就只有这两个区域有内容，背景大面积留白。封面和章节页尤其明显：layout 定义的装饰元素是固定的占位符，Agent 无法根据实际内容调整。

**super_freedom 方案（当前）：**

完全释放创作自由度，模板和布局仅为参考信息注入 Prompt。Agent 自行决定所有元素的 position/size/style，可以自由添加背景（solid/gradient/image）、装饰形状、SVG 图标。解决了 freedom 的 "背景太空" 问题。但代价是**跨页一致性下降**——没有模板强制约束，不同 slide 的设计风格可能差异较大，依赖 Prompt 中的设计规范约束。

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
    │       选择 color_scheme + layout → 写入 presentation 表
    │       同步 style 到所有 presentation_slides（color_scheme_id + template_id）
    │
    ├── Phase 2: Dispatcher (纯代码，无 LLM)
    │   ┌─ 预先创建所有 presentation_slides（batch insert）
    │   ├─ asyncio.gather 并发调度所有 slides
    │   ├─ 每 slide 独立 DB session
    │   ├─ asyncio.Queue → SSE 实时推送 (slide_start / slide_end / retry_round)
    │   └─ 每 slide 调用 SuperFreedomAgent:
    │       ├─ read_instruction() 读取 JSON Schema
    │       ├─ search_icons() 搜索 SVG 图标
    │       └─ submit_slide_instruction(background, elements, notes)
    │              ↓
    │          agent_outputs["super_freedom"] → presentation_slides 表
    │
    └── Assembly
         读取所有 slides 的 agent_outputs → 构建 instruction JSON
         → generate_ppt() → python-pptx 渲染 → {pres_id}.pptx
         → create_snapshot() → 写入 DB
         → update_presentation_status("completed")
```

**指令系统**：`resources/instructions/*.json` 定义每种元素的 JSON Schema。Agent 通过 `read_instruction("textbox.json")` 等工具读取。`HOW_TO_READ.md` 说明类型约定（`string|null`、`hex[]` 等）。

**元素数据类型**：TextboxElement（文本框）、TableElement（表格）、PictureElement（SVG 图标经 cairosvg→PNG 嵌入）、ChartElement（python-pptx 原生图表）、ShapeElement（装饰形状，182 种）。所有元素经 `validator.py` 校验后才写入 DB。

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
    mode: "super_freedom"    # sub_agent (deprecated) | freedom (deprecated) | super_freedom
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
