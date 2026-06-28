# PPTGenius 开发历程与架构演进

> 版本: 0.3.0 | 日期: 2026-06-18

---

## 目录

- [PPTGenius 开发历程与架构演进](#pptgenius-开发历程与架构演进)
  - [目录](#目录)
  - [1. 架构演进时间线](#1-架构演进时间线)
  - [2. Phase 1: CLI 原型](#2-phase-1-cli-原型)
  - [3. Phase 2: Web 化 — Coordinator + LangGraph](#3-phase-2-web-化--coordinator--langgraph)
  - [4. Phase 3: Unified Master Agent 重构](#4-phase-3-unified-master-agent-重构)
  - [5. PPT 生成管线演进](#5-ppt-生成管线演进)
  - [6. 被放弃的方案](#6-被放弃的方案)
  - [7. 过度设计反思](#7-过度设计反思)
  - [8. 关键技术决策记录](#8-关键技术决策记录)
  - [9. 代码量统计](#9-代码量统计)

---

## 1. 架构演进时间线

```
2026-05  ──────── Phase 1: CLI 原型 ──────────────────────────
                  ChromaDB + sentence-transformers
                  单 Agent，CLI 交互
                  ~35s 端到端

2026-06-04 ───── Phase 2: Web 化 ─────────────────────────────
                  Coordinator → Outline Graph → PPT Graph
                  Generator-Evaluator 循环
                  三种 PPT 管线 (sub_agent / freedom / super_freedom)
                  FastAPI + Vue3 前端

2026-06-10 ───── Phase 3: Unified Master ─────────────────────
                  单一 Master Agent 替代 Coordinator + Graphs
                  Sub-agent 以 tool 形式平铺
                  Middleware 三层架构
                  Part-based Slide Agent

2026-06-15 ───── Phase 3.5: 质量改进 ────────────────────────
                  空间检查 (重叠/越界/文字溢出)
                  装饰风格统一 (emoji vs icon)
                  字号体系 (4 级)
                  修改模式容错
```

---

## 2. Phase 1: CLI 原型

**技术栈**: Python CLI + ChromaDB + sentence-transformers + DeepSeek API

**架构**: 单一 Agent 循环，无 sub-agent 分层。
- RAG: ChromaDB 向量检索 + embedding 模型
- PPT: 固定模板，matplotlib 生成图表图片嵌入
- 交互: 命令行输入/输出

**性能基线**: ~35-40s 端到端，~6K tokens/session

**存在问题**:
- 向量检索质量不稳定，依赖 embedding 模型质量
- 固定模板限制设计灵活性
- 无持久化，无多轮对话

**参考文件**: `docs/design/formal-development-plan.md`

---

## 3. Phase 2: Web 化 — Coordinator + LangGraph

**技术栈**: FastAPI + Vue3 + MySQL + LangGraph + BM25

**架构**: 三级 Agent 分层

```
Coordinator (意图分类 → 分发)
  ├── Outline Graph (LangGraph StateGraph)
  │     ├── Generator Node (搜索 + 写大纲)
  │     ├── Evaluator Node (评分 + 建议)
  │     └── 循环直至评分达标或超次数
  └── PPT Graph (LangGraph StateGraph)
        ├── Phase 1: StyleAgent (配色 + 布局)
        └── Phase 2: Dispatcher (并发 slide 生成)
```

**关键设计决策**:

1. **放弃 ChromaDB → BM25**: 中文场景下 BM25 比向量检索更稳定，无需 embedding 模型，部署更简单
2. **Generator-Evaluator 循环**: Generator 生成大纲 → Evaluator 打分 (结构/逻辑/全面性/视觉多样性) → 不达标则重做。实践中发现 Evaluator 打分标准不稳定，且增加了一倍 token 消耗
3. **Coordinator 意图分类**: 用 LLM structured output 分类 (generate_outline / modify_outline / generate_ppt / modify_ppt)，实践中发现分类准确率不如直接给 Master Agent 所有工具让它自行决策

**存在问题**:
- Coordinator 分类偏差导致用户意图被误判
- Generator 内同时承担"搜索"和"写大纲"两个任务，LLM 容易陷入搜索循环不写大纲
- PPT Graph 的 StateGraph 导致 context window 累积（前一轮的 tool_call/result 全保留）
- 三种 PPT 管线 (sub_agent/freedom/super_freedom) 维护成本高

**保留经验**：旧架构代码已在 Phase 3 重构后清理，其设计思路记录于本文档。

**参考文件**: `docs/implement/coordinator_agent.md`, `docs/implement/outline_agent.md`, `docs/implement/ppt_agent.md`

---

## 4. Phase 3: Unified Master Agent 重构

**核心改动**: 删除 Coordinator + Graphs，用单一 Master Agent 替代。

**动机**:
1. Coordinator 意图分类成为瓶颈——误分类无法恢复
2. LangGraph StateGraph 的 context 累积导致 token 爆炸
3. Sub-agent 以独立 LLM 调用运行，context 完全隔离

**设计原则**:
- Master 拥有 19 个 tool（感知 9 + 结构 4 + 执行 6），自行决策调用顺序
- Sub-agent 是 tool——被调用时启动新 LLM，结束后返回一行确认
- 产出写 DB，不走 tool result（避免 Master context 膨胀）
- Middleware 替代手工消息持久化

**关键改进**:
- Generator/Explore 分离：Explore 只搜索产出 section 划分 + 引用 ID → Generator 只写大纲（无搜索工具）
- Outline section 并行化：Master 调用 `outline_section` N 次（每 section 一个 sub-agent），`asyncio.gather` 并发执行
- Slide Agent Part-Based 模型：submit_plan → submit_element × N → check_parts，纯内存操作

**参考文件**: `docs/design/improvement.md`, `docs/implement/problem.md`

---

## 5. PPT 生成管线演进

### 5.1 Sub-Agent 管线（Phase 2 早期）

每页 slide 由 Supervisor 分派给专门化的 Agent：
- TextAgent: 纯文本元素
- ChartAgent: 图表
- ShapeAgent: 装饰图形

**放弃原因**: 分派逻辑复杂，LLM 难以决定"这段内容用 chart 还是 table"，且多个 Agent 之间无协调导致元素位置冲突。

### 5.2 Freedom 管线（Phase 2 中期）

单个 Agent 生成整页所有元素，但仍在 PPT Graph 的 StateGraph 中运行。

**放弃原因**: StateGraph 的 context 累积问题——前一页的工具调用历史对后一页无用但占用 window。

### 5.3 Super Freedom 管线（Phase 2 后期）

单个 Agent，完全独立的 LLM 调用（不走 StateGraph），但仍使用旧的 `submit_element` 单工具模型。

**放弃原因**: 缺乏 Part-based 规划，LLM 直接提交元素容易混乱（不知道何时结束、缺乏进度追踪）。

### 5.4 当前: Part-Based 模型 (`agent/ppt/slide_agent.py`)

引入 `submit_plan` 和 `check_parts` 工具：
- `submit_plan`: 先规划 slide 分区（标题区、内容区、图表区...），声明 bounds
- `submit_element`: 元素归属某个 part
- `check_parts`: 查看/标记 part 完成

**优势**: LLM 有明确的目标和进度追踪，空间规划在提交元素前完成，减少位置冲突。

---

## 6. 被放弃的方案

| 方案 | 阶段 | 放弃原因 |
|------|------|---------|
| ChromaDB 向量检索 | Phase 1 → 2 | 中文 BM25 更稳定，无需 embedding 模型 |
| Evaluator 评分循环 | Phase 2 → 3 | 打分标准不稳定，token 消耗翻倍，改为 Master 直接决策质量 |
| Coordinator 意图分类 | Phase 2 → 3 | 分类错误不可恢复，Unified Master 自行决策更灵活 |
| templates + color_schemes 表 | Phase 2 → 3 | 合并为 styles 表，减少 join |
| Layout 定义文件 (7 types) | Phase 2 → 3 | 改为 template JSON catalog，Slide Agent 自由选择 |
| PPT sub_agent 管线 | Phase 2 | 专门化 Agent 间无协调，位置冲突 |
| PPT freedom 管线 | Phase 2 | StateGraph context 累积 |
| Generator 搜索+写大纲一体化 | Phase 2 → 3 | LLM 陷入搜索循环不写大纲，分离为 Explore + Generator |
| matplotlib 图表图片 | Phase 1 → 2 | 改为 python-pptx 原生图表，可编辑 |
| 三段式版本号 (major.minor.patch) | Phase 2 → 3 | 简化为单调递增 int |

---

## 7. 过度设计反思

### 7.1 三套 PPT 管线并存

Phase 2 同时实现了 sub_agent、freedom、super_freedom 三种管线，通过配置切换。实际只用了 super_freedom，另外两套成为死代码。**教训：先验证一种方案，确认不行再尝试下一种，而非同时实现多种。**

### 7.2 Generator-Evaluator 循环

为大纲生成设计了 Generator + Evaluator 两个节点的循环评估机制。实践中 Evaluator 的打分标准（结构清晰度、逻辑连贯性、全面性、视觉多样性）难以量化，且每轮额外消耗 ~4K tokens。**教训：LLM-as-judge 在开放式创作任务中不如人类反馈，应让用户决定质量是否达标。**

### 7.3 Layout 布局体系

为 PPT 定义了 7 种 layout type（title, content, two_column, image_text, chart_focus, comparison, thanks），每种有固定的元素区域定义。实践中 LLM 难以准确选择 layout 类型，且固定区域限制了设计灵活性。**最终改为 Part-Based 模型，LLM 自行规划分区。教训：与其限定选项让 LLM 选择，不如给工具让它自由规划。**

### 7.4 Coordinator 意图分类

专门设计了一个分类步骤将用户意图映射到四类（生成/修改 × 大纲/PPT）。实际用户意图常混合（"帮我改一下大纲然后生成 PPT"），单一分类无法处理。**教训：ReAct Agent 本身就能决策工具调用顺序，额外的分类层反而是瓶颈。**

### 7.5 当前代码中仍存在的过度设计倾向

- Phase 2 的旧架构代码（~5,300 行）已在 Phase 3 重构完成后清理删除
- `perception.py` (362 行) 的 9 个只读工具中部分使用频率极低
- `spatial_check.py` 的文字溢出估算逻辑较复杂，实际 LLM 很少依据此信息调整

---

## 8. 关键技术决策记录

| 决策 | 选项 | 选择 | 理由 |
|------|------|------|------|
| RAG 引擎 | ChromaDB vs BM25 | BM25 | 中文关键词检索更稳定，无 embedding 模型依赖 |
| LLM 提供商 | OpenAI vs DeepSeek | DeepSeek V4 Flash | 成本低 10x，支持 thinking mode |
| Agent 框架 | LangGraph StateGraph vs ReAct | ReAct (create_agent) | StateGraph context 累积严重 |
| 前端框架 | React vs Vue | Vue 3 + Element Plus | 团队熟悉度 |
| 数据库 | SQLite vs MySQL | MySQL (asyncmy) | 异步支持好，生产环境可扩展 |
| PPT 渲染 | python-pptx vs libreoffice | python-pptx | 可编辑输出，无外部依赖 |
| 搜索引擎 | DuckDuckGo vs SearXNG | 可配置切换 | DDG 被限流时切 SearXNG |
| 图标来源 | FontAwesome vs Tabler | Tabler Icons | MIT 开源，SVG 质量高 |
| Token 统计 | 全局 vs 双层 | 双层 (conv + agent) | Sub-agent 粒度统计费用 |
| 版本号 | 三段式 vs 单调递增 | 单调递增 int | 简单可靠，减少比较复杂度 |

---

## 9. 代码量统计

截止 2026-06-18:

| 类别 | 文件数 | 代码行数 | 说明 |
|------|--------|---------|------|
| agent/ (新) | ~30 | ~4,500 | Unified Master + sub-agents |
| api/ | ~17 | ~1,700 | FastAPI routers + schemas |
| infrastructure/ | ~45 | ~5,500 | DB, RAG, PPT engine, LLM |
| resources/ | N/A | N/A | prompts, styles, fonts |
| tests/ | ~20 | ~2,500 | pytest 单元测试 |
| **合计 (不含旧代码)** | **~112** | **~14,200** | |
| 前端 (Vue3) | ~30 | ~4,000 | views + components + stores |

平均文件 ~130 行，中位数 < 100 行。超 300 行文件 8 个，超 500 行文件 1 个（`ppt_engine/parser/base.py`）。
