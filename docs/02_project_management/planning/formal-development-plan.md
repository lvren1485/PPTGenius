# PPTGenius 正式版开发计划

> 基于 [function-analysis.md](function-analysis.md) 需求 + 原型 `agent-prototype` 分支实验结论
> 选定技术路线：DeepSeek + ChromaDB + sentence-transformers + 5种内置Layout
> 日期：2026-05-21

---

## 一、技术路线总览

```
LLM:         DeepSeek v4-flash (OpenAI兼容SDK)
向量库:      ChromaDB (持久化HNSW索引)
Embedding:   sentence-transformers / all-MiniLM-L6-v2 (384维, 本地)
分块策略:    paragraph (chunk_size=500, overlap=50)
PPT布局:     5种内置Layout (Title/Section/Content/TwoColumn/Ending)
视觉模板:    6-8套 (含暗色/学术/创意风格)
Agent架构:   混合模式 (直接大纲生成 + 可选工具增强)
工具解析:    结构化输出 (chat_structured + JSON mode)
应用架构:    PPTGeniusAgentAPP 入口类 + 无状态设计 (API key/上下文由外部传入)
RAG归属:     App实例内部组件，每个实例独立资源路径
图表:        matplotlib → PNG嵌入
图片:        内置库 + DuckDuckGo搜索
CLI:         argparse
```

### 已确认的性能基线

| 指标 | 数据 |
|------|------|
| LLM 调用延迟 | 1.3-2.5s (简单), 32s (大纲生成) |
| PPT 生成 | 16ms / 5 slides |
| ChromaDB 查询 | 156ms (100条) |
| 端到端 pipeline | 35-40s (含1次大纲LLM调用) |
| 总 token 消耗 | ~6K / 完整session |
| 文件大小 | ~46KB / 12 slides |

---

## 二、正式版架构

```
外部传入:
  ├── api_key                  # 父项目按请求传入，不同客户不同 key
  ├── session_history          # 父项目管理对话上下文
  ├── workspace_path            # 工作空间路径（含RAG数据/状态/历史）
  └── language                 # 生成语言 (en/zh/ja/...)
              │
              ▼
     PPTGeniusAgentAPP (入口类)
         constructor / setter 链
              │
              ├── 1. 启动: 扫描 resources/ → 解析文件 → ChromaDB向量化
              │       └── 真实Embedding (sentence-transformers)
              │
              ├── 2. 规划 + 内容生成 (per-page)
              │       ├── PlanningAgent → 结构规划 + 每页大纲
              │       ├── RAGEngine → 按每页大纲检索知识
              │       └── ContentAgent → 逐页生成内容
              │
              ├── 3. 视觉美化 (BeautifyAgent)
              │       ├── search_web_image → 配图
              │       ├── generate_image → 生成图片
              │       ├── generate_chart → 图表嵌入
              │       └── adjust_layout → 布局微调
              │
              ├── 4. PPT生成 (python-pptx, ~16ms)
              │       ├── 加载template.pptx (含自定义Layout)
              │       ├── 按outline逐页构建
              │       └── 应用模板颜色/字体
              │
              ├── 5. 审查报告 (ReviewerAgent)
              │       └── output/{session_id}_report.md
              │
              ├── 6. 保存对话历史 → 由外部父项目决定
              └── 7. LogCapture → logs/calls/*.md
```

---

## 三、实现阶段

### Phase 1 — RAG 管道真正可用（1-2天）

| 步骤 | 内容 | 文件/命令 |
|------|------|----------|
| 1.1 | `uv add sentence-transformers` 安装本地embedding模型 | 终端 |
| 1.2 | 验证embedder.py中的LocalEmbedder正常工作 | `rag/embedder.py` |
| 1.3 | 验证ChromaDB + 真实embedding的搜索质量 | `rag/vector_store.py` |
| 1.4 | 用真实PDF测试RAG全链路 (解析→分块→embed→搜索) | 放入 resources/ 测试文件 |
| 1.5 | 移除 MockEmbedder 和 JSONVectorStore 回退代码 | `rag/embedder.py` + `rag/vector_store.py` |

**交付物：** RAG 检索可返回语义相关结果。

### Phase 2 — 工具增强链路（2-3天）

| 步骤 | 内容 | 文件 |
|------|------|------|
| 2.1 | ppter.py: 大纲生成后进入工具增强循环 | `agents/ppter.py` |
| 2.2 | 增强循环: 对每个slide, LLM判断是否需要工具调用 | `agents/ppter.py` |
| 2.3 | query_knowledge_base → 补充slide内容 | `agents/tools/knowledge.py` |
| 2.4 | search_web → 获取最新数据/引用 | `agents/tools/search_web.py` |
| 2.5 | generate_chart → 生成图表PNG并嵌入slide | `agents/tools/generation.py` + `ppt/charts.py` |
| 2.6 | select_image → 添加配图 | `agents/tools/images.py` + `ppt/images.py` |
| 2.7 | 工具调用全部通过chat_structured实现 | `llm/openai_client.py` |

**核心设计：** 工具增强循环不是原来的 ReAct 循环，而是 **逐 slide 的"检查-填补"模式**——LLM 一次性生成完整大纲后，逐页判断是否需要补充数据/图表/图片，需要则调用对应工具，将结果合并回该 slide 内容。

**交付物：** PPT 中包含真实数据和图表的 slide。

### Phase 3 — PPT 品质提升（2-3天）

| 步骤 | 内容 | 文件 |
|------|------|------|
| 3.1 | 扩展模板到6-8套 (Dark Mode, Academic, Creative) | `ppt/templates.py` |
| 3.2 | 图表自动嵌入slide (charts.py → slide.add_picture) | `ppt/generator.py` |
| 3.3 | 图片自动嵌入slide (images.py → slide.add_picture) | `ppt/generator.py` |
| 3.4 | 新增 layout: 流程图、时间线、对比表 | `ppt/slides.py` |
| 3.5 | two_column 布局优化 (奇数bullet处理) | `ppt/slides.py` |
| 3.6 | 增加 section slide 的进度指示 | `ppt/slides.py` |
| 3.7 | 模板可视化预览 (markdown of color schemes) | `docs/templates.md` |

**交付物：** 视觉专业的 PPT，含嵌入式图表和图片。

### Phase 4 — 多轮对话与修改（1-2天）

| 步骤 | 内容 | 文件 |
|------|------|------|
| 4.1 | `--session-id` 恢复时加载已有PPT路径 | `agents/orchestrator.py` |
| 4.2 | modify_slide_content 实际修改python-pptx对象 | `agents/tools/modification.py` |
| 4.3 | modify_slide_layout 切换slide layout | `agents/tools/modification.py` |
| 4.4 | 多轮场景测试: 生成→修改→再修改 | 手动测试 |

**交付物：** 多轮对话可修改已生成 PPT 的内容和布局。

### Phase 5 — 工程化（2-3天）

| 步骤 | 内容 | 文件 |
|------|------|------|
| 5.1 | 完整的错误处理链 (LLM超时、工具异常、文件缺失) | 全模块 |
| 5.2 | 进度反馈 (stdout逐步输出 + 可选yield) | `cli.py` |
| 5.3 | integration tests (端到端) | `tests/test_e2e.py` |
| 5.4 | 移除所有mock代码 (MockLLMClient, MockEmbedder) | 清理 |
| 5.5 | 量化评估: PPT逻辑评分、知识溯源、多领域测试 | `tests/evaluation/` |
| 5.6 | 经济评估: token用量统计和费用估算 | `logger.py` 扩展 |
| 5.7 | 文档完善: README, 配置说明, API参考 | `docs/` |

**交付物：** 生产级可用的 PPTGenius。

---

## 四、代码结构（正式版）

```
src/pptgenius_agent/
├── __init__.py          # 版本号, 导出 PPTGeniusAgentAPP
├── __main__.py          # CLI 入口 (python -m), 单行委托给 cli
├── app.py               # PPTGeniusAgentAPP 入口类 (constructor + setter 链)
├── cli.py               # argparse 解析 + 组装 APP → 调用 run()
├── config.py            # 配置 (默认值 + CLI 传入覆盖)
├── logger.py            # LogCapture + token 统计
│
├── llm/
│   ├── base.py          # LLMClient 抽象基类
│   └── openai_client.py # OpenAI SDK (兼容DeepSeek)
│
├── models/
│   ├── outline.py       # PresentationOutline, SlideOutline, Plan, TodoItem
│   └── conversation.py  # 对话记录模型
│
├── db/
│   ├── engine.py        # SQLite连接管理 (仅本地调试/日志)
│   ├── conversation.py  # 会话CRUD (由外部父项目主管理)
│   └── structured_data.py # CSV/xlsx导入查询
│
├── rag/
│   ├── scanner.py       # 文件扫描+注册
│   ├── parsers/         # PDF/DOCX/PPTX/TXT/CSV解析器
│   ├── chunker.py       # 文本分块 (paragraph默认)
│   ├── embedder.py      # sentence-transformers / OpenAI
│   └── vector_store.py  # ChromaDB (按 workspace 路径隔离)
│
├── agents/
│   ├── orchestrator.py  # 顶层协调器 (含状态追踪 + 结构化决策)
│   ├── planning.py      # PPT结构规划
│   ├── content.py       # 逐页内容生成 (接收 planning + RAG)
│   ├── beautify.py      # 视觉美化 (搜图/图表/布局微调)
│   ├── diagram.py       # 图表生成
│   ├── reviewer.py      # 审查agent (总结 + 改进建议)
│   └── tools/           # 工具注册
│       ├── registry.py  # 工具注册表
│       ├── knowledge.py # RAG检索
│       ├── database.py  # SQL查询
│       ├── search_web.py # DuckDuckGo搜索
│       ├── template.py  # 模板选择
│       ├── modification.py # PPT修改
│       ├── generation.py   # PPT/图表/表格生成
│       ├── images.py    # 图片选择
│       └── planner.py   # 规划工具
│
├── ppt/
│   ├── generator.py     # PPT生成主逻辑
│   ├── templates.py     # 6-8套模板定义
│   ├── slides.py        # 5种Layout构建
│   ├── styles.py        # 颜色/字体常量
│   ├── charts.py        # matplotlib图表
│   └── images.py        # 图片查询
│
├── resources/
│   ├── prompts/         # LLM prompt 模板 (含 {language} 占位符)
│   │   ├── orchestrator.md  # 含 {current_phase}, {message}, {slide_count} 等状态占位符
│   │   ├── planning.md
│   │   ├── content.md   # 接收 {planning_structure} + {rag_results}, 逐页生成
│   │   ├── beautify.md  # 三阶段: Template Design → Style Guide → Apply
│   │   ├── diagram.md
│   │   └── reviewer.md  # 接收 {ppt_content}, 输出总结+建议
│   ├── schema.sql       # 数据库结构
│   └── ...              # PPT 模板等静态资源
├── data/                # 运行时数据 (按 workspace 可配置)
├── config.yaml          # 默认配置 (被构造器传入值覆盖)
└── logs/                # 日志输出
```

---

## 五、API 接口定义

### CLI 接口
```bash
# 基础使用
pptgenius --message "主题" --session-id <uuid>

# 常用选项
--output-dir ./my_ppts    # 输出目录
--template modern-teal    # 指定模板
--model deepseek-v4-flash # 指定模型
--slides 15               # 指定目标幻灯片数
--dry-run                 # 仅生成大纲JSON，不生成PPT
--workspace ./workspace   # 工作空间路径 (状态/RAG/历史持久化)
--language zh             # 生成语言 (默认 en)
```

### Python 包调用 — PPTGeniusAgentAPP 入口类

`generate_presentation()` 是生成器函数，CLI 和包调用共用同一套遍历接口：

```python
from pptgenius_agent import PPTGeniusAgentAPP

# 方式一: 构造器
app = PPTGeniusAgentAPP(
    api_key="sk-xxx",
    api_base_url="...",
    model="deepseek-v4-flash",
    workspace_path="/data/tenant_a/",
)

for event in app.generate_presentation():
    if event["type"] == "llm_call":
        print(f"LLM调用: {event['call_type']}")
    elif event["type"] == "tool_call":
        print(f"工具: {event['tool_name']}")
    elif event["type"] == "progress":
        print(f"进度: {event['message']}")
    elif event["type"] == "done":
        print(f"完成: {event['output_path']}")

# 方式二: setter 链 (CLI 路径风格)
app = PPTGeniusAgentAPP() \
    .set_api_key("sk-xxx") \
    .set_session_id("my-session") \
    .set_workspace_path("/data/tenant_b/")

for event in app.generate_presentation():
    if event["type"] == "done":
        result = event["output_path"]
```

---

## 六、需要的外部资源

| 资源 | 用途 | 状态 | 成本 |
|------|------|------|------|
| DeepSeek API Key | LLM 调用 | ✅ 已有 | 按token计费 (~¥2/百万tokens) |
| sentence-transformers | 本地Embedding | 🔲 需安装 | 免费 (~80MB模型下载) |
| chromadb | 向量存储 | ✅ 已安装 | 免费 |
| 测试用 PDF/DOCX | RAG 测试 | 🔲 需放入 resources/ | — |
| DALL-E API Key | 图片生成 | ❌ 暂缺 | 用 DuckDuckGo 替代 |
| plotly | 交互图表的静态图 | 🔲 可选 | `uv add plotly` |

---

## 七、关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| Agent 不拆分多agent | 单一 orchestrator + tool registry | 原型验证显示单agent足够，多agent通信开销大于收益 |
| 内容修改和布局修改分开 | 两个独立工具 | 操作python-pptx的代码路径完全不同，分开更清晰 |
| 文件注册表用 SQLite 而非 JSON | SQLite 表 | 支持按状态查询、错误信息记录、大量文件遍历 |
| 每个文件 ≤ 300 行 | 超限则拆分 | 保持代码可维护性 |
| 不使用 async | 同步单线程 | 原型阶段不需要，简化调试 |
| 不使用文件监控守护 | 启动时一次性扫描 | 简化实现，满足原型需求 |
| **子项目无状态化** | PPTGeniusAgentAPP 入口类 | API key、对话历史由外部传入，多租户隔离 |
| **Workspace 归属 App 实例** | 每个实例独立 workspace_path | 所有状态（RAG/对话历史/大纲）统一存储在 workspace 中 |
| **入口类双路径设计** | constructor + setter 链 | CLI 路径逐步填入参数，包调用路径构造函数一次性传入 |
| **内容+美化分离** | PPTAgent 生成内容 → BeautifyAgent 后美化 | 图片/图表依赖具体内容，先有内容才知道配什么图 |
| **多语言支持** | prompt 模板 `{language}` 占位符 | 一套 prompt 模板，运行时注入目标语言 |

---

## 八、评估方案

### 定量评估
```python
# 每次运行自动统计:
{
    "session_id": "...",
    "total_tokens": 6234,
    "llm_calls": 2,
    "total_time_seconds": 35.2,
    "ppt_size_kb": 46.2,
    "slide_count": 12,
    "tool_calls": 5,
    "estimated_cost_usd": 0.003,
}
```

### 质量评估
- **知识溯源率**: RAG 检索的 slide 中有 % 的内容可追到源文件
- **布局多样性**: 一次生成中使用了多少种 layout_type
- **多领域适配**: 科技/医疗/教育各测试 3 次, 评估内容专业度

---

## 九、当前状态

```
Phase 1 (RAG管道)  ████████░░  80%  — 缺 sentence-transformers 安装验证
Phase 2 (工具增强)  ██░░░░░░░░  20%  — 工具已实现, 链路未接通
Phase 3 (PPT品质)   ████████░░  80%  — layout/模板已OK, 缺图表图片嵌入
Phase 4 (多轮对话)  ██░░░░░░░░  20%  — modify工具框架已建, 缺实际实现
Phase 5 (工程化)    █░░░░░░░░░  10%  — 框架已建, 缺完善
```

> 正式版将在清理原型后使用 `main` 分支开始，当前 `agent-prototype` 分支的代码作为参考。
