# PPTGenius 开发历程与架构演进

> 版本: 0.4.0 | 日期: 2026-06-19

---

## 目录

- [PPTGenius 开发历程与架构演进](#pptgenius-开发历程与架构演进)
  - [目录](#目录)
  - [1. 架构演进时间线](#1-架构演进时间线)
  - [2. Phase 1: CLI 原型与技术验证](#2-phase-1-cli-原型与技术验证)
  - [3. Phase 2: Web 化 — Coordinator + LangGraph](#3-phase-2-web-化--coordinator--langgraph)
  - [4. Phase 3: Unified Master Agent 重构](#4-phase-3-unified-master-agent-重构)
  - [5. 大纲生成管线演进](#5-大纲生成管线演进)
  - [6. PPT 生成管线演进](#6-ppt-生成管线演进)
  - [7. Slide Agent 工具模型演进](#7-slide-agent-工具模型演进)
  - [8. 被放弃的方案](#8-被放弃的方案)
  - [9. 设计反思](#9-设计反思)
  - [10. 关键技术决策记录](#10-关键技术决策记录)
  - [11. 代码量统计](#11-代码量统计)

---

## 1. 架构演进时间线

```
04-10 ~ 04-26  Phase 1: CLI 原型与技术验证 ───────────────────
                 ChromaDB + sentence-transformers + DeepSeek API
                 单 Agent 循环，CLI 交互
                 验证: LLM 可生成结构化大纲，RAG 可增强内容

04-27 ~ 05-10  Phase 2a: Web 架构搭建 ────────────────────────
                 FastAPI + Vue3 + MySQL + BM25
                 基础 API / 前端 / DB 层搭建
                 M1 评审 (05-10)

05-10 ~ 06-06  Phase 2b: Agent 架构 + PPT 管线迭代 ──────────
                 Coordinator → Outline Graph → PPT Graph
                 Generator-Evaluator 循环
                 PPT 管线渐进式迭代:
                   Sub-Agent → Freedom → Super Freedom
                 M2 评审 (06-06)

06-06 ~ 06-12  Phase 3: Unified Master 重构 ──────────────────
                 单一 Master Agent 替代 Coordinator + Graphs
                 Sub-agent 以 tool 形式平铺
                 Middleware 三层架构
                 Slide Agent 工具模型迭代:
                   一次性提交 → 逐步提交 → Part-Based + Plan

06-12 ~ 06-18  Phase 3.5: 质量改进 ──────────────────────────
                 空间检查 (重叠/越界/文字溢出)
                 装饰风格统一 (emoji vs icon)
                 字号体系 (4 级) / 文本密度
                 修改模式容错
```

---

## 2. Phase 1: CLI 原型与技术验证

**时间**: 04-10 ~ 04-26 | **目标**: 验证技术路线可行性

**技术栈**: Python CLI + ChromaDB + sentence-transformers + DeepSeek API

**架构**: 单一 Agent 循环，无 sub-agent 分层。
- RAG: ChromaDB 向量检索 + embedding 模型
- PPT: 固定模板，matplotlib 生成图表图片嵌入
- 交互: 命令行输入/输出

**性能基线**: ~35-40s 端到端，~6K tokens/session

**验证结论**:
- LLM (DeepSeek) 能够生成结构合理的 PPT 大纲
- 向量检索在中文场景下质量不稳定，依赖 embedding 模型
- 固定模板限制设计灵活性，需要更自由的生成方式
- 无持久化 / 无多轮对话，无法支撑产品化

**阶段产出**: 技术可行性确认 → 决定转向 Web 架构 + BM25

---

## 3. Phase 2: Web 化 — Coordinator + LangGraph

**时间**: 04-27 ~ 06-06 | **目标**: 构建完整 Web 应用

### 3.1 Phase 2a: Web 架构搭建 (04-27 ~ 05-10)

搭建基础技术框架和核心管线：
- **后端 infrastructure 层**: FastAPI + MySQL (asyncmy + SQLAlchemy 2.0)，DB 模型、Repository 层、配置体系、工作区管理、日志系统
- **RAG 管线**: 放弃 ChromaDB，改用 BM25（中文场景更稳定、无需 embedding 模型）；实现文件上传、多格式解析 (PDF/DOCX/XLSX)、文本分块、BM25 索引
- **简单大纲生成器**: 基于单次 LLM 调用直接输出 JSON 结构化大纲（无 Agent 循环、无 Evaluator），验证 DeepSeek API 生成大纲的基本能力
- **Demo 前端**: Vue 3 + Element Plus 搭建对话界面、文件上传、大纲展示等基础页面
- **消息持久化 + SSE 流式通信**: 建立前后端实时通信机制
- M1 评审 (05-10)

### 3.2 Phase 2b: Agent 架构 + PPT 管线迭代 (05-10 ~ 06-06)

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

1. **Generator-Evaluator 循环**: Generator 生成大纲 → Evaluator 打分 → 不达标则重做。实践中发现 Evaluator 打分标准不稳定，且每轮额外消耗 ~4K tokens
2. **Coordinator 意图分类**: 用 LLM structured output 分类四种意图。实践中发现分类准确率不如直接给 Master Agent 所有工具让它自行决策
3. **PPT 管线渐进式迭代**: 详见 [§5 PPT 生成管线演进](#5-ppt-生成管线演进)

**存在问题**:
- Coordinator 分类偏差导致用户意图误判（如"改大纲再生成PPT"被分类为单一类型）
- Generator 同时承担"搜索"和"写大纲"，LLM 容易陷入搜索循环
- StateGraph 的 context 累积——前一轮 tool_call/result 全保留，token 爆炸

**M2 评审 (06-06)**: 系统端到端可用，14 轮对话测试，大纲平均分 8.19/10。评审后决定进行 Unified Master 重构。

---

## 4. Phase 3: Unified Master Agent 重构

**时间**: 06-06 ~ 06-12 | **目标**: 简化架构、降低 token 消耗

**核心改动**: 删除 Coordinator + StateGraph Graphs，用单一 Master Agent 替代。

**动机**:
1. Coordinator 意图分类成为瓶颈——误分类无法恢复
2. LangGraph StateGraph 的 context 累积导致 token 爆炸（单次 PPT 生成 ~40K tokens → 重构后 ~14K）
3. Sub-agent 以独立 LLM 调用运行，context 完全隔离

**设计原则**:
- Master 拥有 19 个 tool（感知 9 + 结构 4 + 执行 6），自行决策调用顺序
- Sub-agent 是 tool——被调用时启动新 LLM，结束后返回一行确认
- 产出写 DB，不走 tool result（避免 Master context 膨胀）
- Middleware（Persist + SSE + Token）替代手工消息持久化

**关键改进**:
- Generator/Explore 分离：Explore 只搜索产出 section 划分 + 引用 ID → Generator 只写大纲（无搜索工具）
- Outline section 并行化：`asyncio.gather` 并发执行多个 section
- Slide Agent 工具模型迭代：详见 [§6 Slide Agent 工具模型演进](#6-slide-agent-工具模型演进)

---

## 5. 大纲生成管线演进

大纲生成管线经历了三个版本的迭代，每次迭代都带来了实际的生成时间缩减：7-8 分钟 → 4-5 分钟 → 2m 25s (benchmark 实测)。相比 PPT 生成管线（7-8 分钟 → 4m 39s 实测，且不稳定），大纲管线的优化效果更为显著。

### 5.1 V1: Generator-Evaluator 循环系统 (~7-8 min)

**设计思路**: Generator Agent 通过搜索知识库 + 网络，一次性生成完整大纲。Evaluator Agent 对生成的大纲按量化问卷逐项评分（结构清晰度、逻辑连贯性、全面性、视觉多样性），给出细节分数和改进建议。不达标则 Generator 根据反馈重新生成，循环直至评分达标或超过最大迭代次数。

**架构**:
```
Generator (搜索 + 生成完整大纲)
    ↓ 大纲
Evaluator (量化评分 + 改进建议)
    ↓ 分数 < 阈值?
    是 → 返回 Generator 重新生成
    否 → 完成
```

**问题**: 整个流程耗时 7-8 分钟。Generator 需要完整生成全部大纲内容（20+ 页），单次生成耗时长；Evaluator 需要逐页检查，评分本身又增加 ~1 分钟。加上可能的重试循环，总时间不可控。

### 5.2 V2: Section 拆分 + 并行生成 (~4-5 min)

**设计思路**: 将"一次性生成完整大纲"拆分为两个阶段——先由 Master 规划 section 结构，再为每个 section 独立生成内容。这样 section 级别的内容生成可以并发执行（`asyncio.gather`），大幅缩短总耗时。

**架构变更**:
```
Master Agent
  ├─ 规划 sections (write_outline_structure)
  ├─ Knowledge Agent (有文件时给出概要总结)
  ├─ Generator × N (每 section 一个，并发执行)
  │     └─ 搜索知识 + 写入 slides
  └─ Evaluator (评估完成度)
```

在这一版中，Generator 和 Evaluator 都被提升为 Master 直接管理的工具。Generator 仍然负责搜索知识库并写入 slide 内容。另外引入了一个 Knowledge Agent，在对话有上传文件时对文件内容给出概要总结，为 Master 规划 section 提供参考。

**观察到的问题**:

1. **Generator 跳过写入**: Generator 拥有搜索工具（`search_knowledge`、`search_web`）和写入工具（`write_slide`），但在实际运行中经常只调用搜索工具就结束，不调用 `write_slide` 写入结果。LLM 在"搜索信息"和"产出内容"两个任务之间摇摆，倾向于认为"搜索到了信息就等于完成了任务"。

2. **Master 规划不合理**: 在没有知识文件的场景下（纯主题生成），Master 对 section 的规划缺乏信息支撑，容易产出过于笼统或不平衡的 section 划分（如"引言 + 正文 + 总结"三段式）。Knowledge Agent 的概要总结有帮助，但在无文件场景下无法发挥作用。

3. **并行搜索重复**: 多个并发 Generator 同时搜索同一个知识库，产生大量重复的 BM25 查询，既浪费 token 又增加延迟。

### 5.3 V3: Explore + Generator 分离 (~2-3 min，当前版本)

**设计思路**: 将 Generator 的"搜索知识"和"生成内容"两个职责彻底分离为两个独立 Agent：

- **Explore Agent**: 负责搜索知识库 + 网络，产出 section 规划和每个 section 所需的知识引用（file_id + chunk_id）
- **Generator**: 只负责根据给定的知识文本生成 slide 内容，**不拥有任何搜索工具**

**架构**:
```
Master Agent
  ├─① explore_knowledge(query)
  │     └─ Explore Agent: search_knowledge + search_web + fetch_web
  │           → 输出 JSON: {sections: [{title, description, file_ids, chunk_ids}]}
  │           → 写入 outlines.explore_result_json
  ├─② write_outline_structure(sections)
  │     → Master 根据 Explore 结果写入 section + slide 结构
  └─③ generate_outline_content()
        └─ Generator × N (每 section 一个，并发)
              → 从 section.citations 读取 file_ids/chunk_ids
              → 从 DB 加载完整 chunk 文本，注入 prompt
              → 只调用 write_slide + pending_slides（无搜索工具）
```

**核心改进及其效果**:

1. **Generator 职能单一化**: Generator 不再拥有搜索工具，prompt 中直接注入了完整的知识文本。它唯一的任务就是"根据这些材料写 slide"。这彻底解决了 V2 中 Generator 跳过写入的问题——没有搜索工具可用，LLM 只能调用 `write_slide`。

2. **消除并行重复搜索**: Explore Agent 只运行一次（单线程），完成所有搜索后产出统一的 section 划分和引用。后续 N 个并发 Generator 各自从 DB 读取已有知识文本，不再发起任何搜索请求。

3. **Section 规划质量提升**: Section 规划从 Master（无知识上下文）转移到 Explore Agent（带有文件摘要 + 搜索结果）。Explore Agent 在充分了解知识内容后规划 section，划分更合理、更贴合实际材料。

4. **知识链路可追溯**: Explore 的引用信息（file_id + chunk_id）从 `explore_result_json` 传递到 `section.citations`，再由 Generator 读取 chunk 全文注入 prompt，最后 Generator 写入 slide 时附带 `citations`。整条链路清晰可追溯。

### 5.4 Evaluator 的最终移除

Evaluator 在 V3 架构中没有被立即移除，而是在实际运行中观察到两个问题后才被删除：

1. **时间开销过大**: Evaluator 需要逐页检查所有 slide 的 content_json，单次评估约需 1 分钟。对于 20 页大纲，这意味着评估本身就占了总时间的 30-50%。

2. **实际作用有限**: 在 V3 的 Explore + Generator 模式下，Generator 的完成率已经非常高（每次都能写完分配的 slides）。Evaluator 的实际作用退化为"确认所有 slide 都已完成"——这通过一个简单的 perception 工具（`get_pending_slides`）就能实现，不需要启动一个完整的 LLM Agent。

移除 Evaluator 后，大纲生成总时间进一步缩短约 1 分钟。

### 5.5 时间对比

| 版本 | 大纲耗时 | PPT 耗时 | 主要瓶颈 |
|------|---------|---------|---------|
| V1 Generator-Evaluator | 7-8 min | 7-8 min | 串行生成 + 评估循环 |
| V2 Section 并行 | 4-5 min | 7-8 min | Generator 搜索耗时 + Evaluator 评估 |
| V3 Explore + Generator | **2m 25s** (实测) | **4m 39s** (实测) | Explore 搜索 (仅一次) |

大纲管线的优化效果比 PPT 更显著，原因在于大纲的瓶颈是"搜索"（可集中执行一次），而 PPT 的瓶颈是"每页独立的 LLM 推理"（无法进一步压缩单页时间，只能靠并发）。

---

## 6. PPT 生成管线演进

PPT 管线的演进是**渐进式探索**的过程——每一步都是对上一步观察到的具体问题的针对性改进，而非预先设计多种方案并行对比。

### 5.1 起点：Sub-Agent 管线 (05-16 ~ 05-20)

**设计思路**: 每页 slide 由 Supervisor 分派给专门化的 Agent——TextAgent 处理文本、ChartAgent 处理图表、ShapeAgent 处理装饰。初衷是让专门化 Agent 各司其职，降低单个 Agent 的认知负荷。

**观察到的问题**: Sub-Agent 完全没有全局排版的概念。TextAgent 把文字放在 (1, 1)、ChartAgent 也把图表放在 (1, 1)，元素彼此重叠。Supervisor 虽然负责分派任务，但无法协调多个 Agent 之间的空间分配——它只知道"这页需要一个标题、两段文字、一个图表"，不知道它们应该放在哪里。

**结论**: 多 Agent 协调空间布局的问题本质上比单 Agent 自行安排更难。**放弃 Sub-Agent，转向单 Agent 生成整页。**

### 5.2 改进一：Freedom 管线 (05-20 ~ 05-24)

**设计思路**: 既然多 Agent 协调困难，改为单个 Agent 生成整页全部元素。但仍保留 Layout 模板系统（7 种 layout type），Agent 在模板预定义的区域内填充内容。

**观察到的问题**: 模板的强制约束导致生成效果不协调。模板定义了固定的背景色和标题样式，但 StyleAgent 选择的配色方案可能与之冲突——比如模板背景是白色，StyleAgent 选了深色主题，结果标题文字颜色与背景接近看不清。Agent 无法自主决定背景和标题样式，只能在模板的"框"里填充。

另外，Freedom 管线仍运行在 PPT Graph 的 StateGraph 中，前一页的生成历史（大量 tool_call/result 消息）保留在 context 中，对后续页面无用但持续消耗 token。

**结论**: 固定模板限制了设计灵活性，且 StateGraph 的 context 累积不可接受。**放弃模板强制，转向完全自由生成 + context 隔离。**

### 5.3 改进二：Super Freedom 管线 (05-24 ~ 06-06)

**设计思路**: 完全自由——不用模板，不用 StateGraph。每页 slide 启动一个独立的 LLM 调用，Agent 自行决定背景、标题、内容元素的所有细节。context 完全隔离，页与页之间互不干扰。

**效果**: 生成质量显著提升。Agent 能够根据 style 配色自行选择协调的背景和元素颜色，不再受模板约束。每页 token 消耗大幅降低（无历史 context 累积）。

这一版本在 M2 评审中使用，得到了较好的评价。但工具模型还有演进空间——详见 [§6](#6-slide-agent-工具模型演进)。

---

## 7. Slide Agent 工具模型演进

Super Freedom 确立了"每页独立 Agent + 完全自由生成"的架构，但**Agent 使用工具的方式**经历了三轮迭代：

### 6.1 一次性全提交 (06-06 ~ 06-08)

**设计**: Agent 通过 `submit_element` 工具逐个提交元素，但没有明确的"完成"信号——Agent 自行判断何时停止。

**观察到的问题**: `validator.py` 对每个元素做 JSON Schema 校验，不通过时 Agent 需要修正后重提交。当一页有 8-10 个元素、每个都可能校验失败时，retry 次数暴增，单页生成时间从 30 秒膨胀到 2-3 分钟。更严重的是，Agent 在多次 retry 后容易"迷失"——忘记还有哪些元素没提交。

**结论**: 需要将"背景"和"元素"分开提交，减少单次提交的校验复杂度。

### 6.2 逐步提交：背景 → 元素 → 笔记 (06-08 ~ 06-10)

**设计**: 将工具拆分为 `submit_background`、`submit_element`、`submit_notes` 三步。Agent 按步骤提交，每步独立校验。

**观察到的问题**: Agent 有时在提交了背景和 3-4 个元素后突然停止（输出 `</s>` 或发出最终回复），导致 slide 是半成品——有标题和背景，但缺少正文内容或图表。LLM 没有一个明确的机制告诉它"你还没做完"。

**结论**: 需要一个显式的**规划 + 进度追踪**机制，让 Agent 知道"还有哪些区域没完成"。

### 6.3 Part-Based + Plan 模型 (06-10 ~)

**设计**: 引入 `submit_plan` 和 `check_parts` 两个工具：

```
submit_plan(parts=[{name, description, bounds}, ...])
  → 定义 slide 的区域规划 (标题区、内容区、图表区...)
  → 每个 part 初始状态为 "pending"

submit_element(element, part="标题区")
  → 元素归属具体的 part

check_parts()
  → 查看所有 part 的状态和元素数量
  → check_parts(part="标题区", complete=true) 标记完成

Agent 退出条件: 所有 part 都标记为 complete
```

**效果**:
- Agent 先规划再执行，空间分配在元素提交前完成
- `check_parts` 提供进度感知——Agent 可以随时查看"还有哪些 part 没完成"
- 退出条件明确——`not incomplete and has_content`，不依赖 LLM 自行判断何时停止
- 即使 Agent 被打断，retry 时可以通过 `check_parts()` 恢复进度

**当前仍存在的挑战**:
- 修改模式下所有 part 初始为 `complete`，LLM 看到后直接退出不做修改（已通过 prompt 修复：要求先 `submit_plan` 重置待修改 part）
- `submit_plan` 的 bounds 预检有时过于严格，导致合理设计被误报

---

## 8. 被放弃的方案

| 方案 | 阶段 | 放弃原因 |
|------|------|---------|
| ChromaDB 向量检索 | Phase 1 → 2a | 中文 BM25 更稳定，无需 embedding 模型 |
| Generator-Evaluator 串行循环 | 大纲 V1 → V2 | 串行生成 7-8min，拆分为 section 并行后降至 4-5min |
| Evaluator 逐页评估 | 大纲 V2 → V3 | 单次 ~1min，实际仅确认完成度，perception 工具可替代 |
| Generator 搜索+写入一体化 | 大纲 V2 → V3 | LLM 搜索后倾向直接结束，跳过 write_slide |
| Master 直接规划 section | 大纲 V2 → V3 | 无知识上下文时规划不合理，改由 Explore 带知识规划 |
| Knowledge Agent (文件概要) | 大纲 V2 → V3 | 被 Explore Agent 的文件摘要注入替代 |
| Coordinator 意图分类 | Phase 2b → 3 | 分类错误不可恢复，ReAct 自行决策更灵活 |
| templates + color_schemes 表 | Phase 2b → 3 | 合并为 styles 表，减少复杂度 |
| Layout 模板定义 (7 types) | Phase 2b → 3 | 强制模板导致背景/标题不协调 |
| Sub-Agent PPT 管线 | Phase 2b | 多 Agent 无法协调空间布局 |
| Freedom + 模板管线 | Phase 2b | 模板约束 + StateGraph context 累积 |
| 一次性全提交工具模型 | Phase 3 | validator 重试导致异常耗时 |
| 逐步提交无 Plan | Phase 3 | Agent 中途停止，slide 半成品 |
| matplotlib 图表 | Phase 1 → 2a | 改为 python-pptx 原生图表，可编辑 |
| 三段式版本号 | Phase 2b → 3 | 简化为单调递增 int |

---

## 9. 设计反思

### 9.1 PPT 管线的渐进式迭代

PPT 管线经历了 Sub-Agent → Freedom → Super Freedom → 一次性提交 → 逐步提交 → Part-Based 共 6 个版本。这一过程**不是**过度设计——每一步都是对上一步观察到的具体问题（排版冲突、模板不协调、重试爆炸、中途停止）的针对性改进。最终的 Part-Based + Plan 模型综合了所有前序版本的教训。

### 9.2 大纲管线的职责拆分

大纲管线的三版迭代揭示了一个核心教训：**不要让同一个 Agent 同时承担"搜索信息"和"产出内容"两个任务**。V2 中 Generator 拥有搜索工具后，LLM 倾向于"搜索 = 完成任务"，跳过实际的内容写入。V3 将搜索职责剥离给 Explore Agent 后，Generator 的完成率从不稳定提升到接近 100%。

这个教训可以推广为：**LLM Agent 的工具集应该在功能上内聚——一组工具服务于一个明确目标，不要混合"获取信息"和"执行动作"两类工具**。这一原则在 Slide Agent 的 Part-Based 模型中也得到验证——所有工具都围绕"构建一页 slide"这个单一目标。

### 9.3 Evaluator 的价值判断

Evaluator 的移除不是因为"评估不重要"，而是因为评估的**边际价值不抵其成本**。在 V1 中 Evaluator 有真实价值（Generator 完成率不稳定时需要质量把关），但到 V3 中 Generator 已经能稳定完成所有 slides，Evaluator 退化为一个昂贵的"完成确认器"。**教训：组件的价值不是静态的——当上游改进消除了下游存在的理由时，应果断移除而非保留。**

### 9.4 Layout 布局体系

为 PPT 定义了 7 种 layout type，每种有固定区域。实践中 LLM 难以准确选择 layout 类型，且固定区域限制了设计灵活性。**最终改为 Part-Based 模型，LLM 自行规划分区。教训：与其限定选项让 LLM 选择，不如给工具让它自由规划。**

### 9.5 Coordinator 意图分类

专门设计分类步骤将用户意图映射到四类。实际用户意图常混合（"帮我改一下大纲然后生成 PPT"），单一分类无法处理。**教训：ReAct Agent 本身就能决策工具调用顺序，额外的分类层反而是瓶颈。**

### 9.6 从过程中沉淀的设计原则

1. **LLM Agent 的工具设计靠迭代，不靠推理**——实际生成效果是唯一可靠的验证手段
2. **给 LLM 自由度比给约束更有效**——Part-Based 比 Layout 模板效果好，Unified Master 比 Coordinator 分类效果好
3. **显式进度追踪防止 Agent 迷失**——check_parts / pending_slides 比"Agent 自行判断完成"可靠得多
4. **Context 隔离是 Agent 架构的核心约束**——StateGraph 共享 context 是 token 爆炸的根源
5. **工具集应功能内聚**——搜索和产出分离，一组工具服务于一个目标
6. **组件价值动态评估**——上游改进后及时移除不再必要的下游组件

---

## 10. 关键技术决策记录

| 决策 | 选项 | 选择 | 理由 |
|------|------|------|------|
| RAG 引擎 | ChromaDB vs BM25 | BM25 | 中文关键词检索更稳定，无 embedding 依赖 |
| LLM 提供商 | OpenAI vs DeepSeek | DeepSeek V4 Flash | 成本低 10x，支持 thinking mode |
| Agent 框架 | LangGraph StateGraph vs ReAct | ReAct (create_agent) | StateGraph context 累积严重 |
| PPT 管线 | Sub-Agent vs Freedom vs Super Freedom | Super Freedom + Part-Based | 渐进式淘汰，最终方案综合前序教训 |
| 大纲管线 | Generator-Evaluator vs Section 并行 vs Explore+Generator | Explore + Generator | 搜索/生成职责分离，7-8min→2-3min |
| 前端框架 | React vs Vue | Vue 3 + Element Plus | 团队熟悉度 |
| 数据库 | SQLite vs MySQL | MySQL (asyncmy) | 异步支持好，生产环境可扩展 |
| PPT 渲染 | python-pptx vs libreoffice | python-pptx | 可编辑输出，无外部依赖 |
| 搜索引擎 | DuckDuckGo vs SearXNG | 可配置切换 | DDG 被限流时切 SearXNG |
| 图标来源 | FontAwesome vs Tabler | Tabler Icons | MIT 开源，SVG 质量高 |
| Token 统计 | 全局 vs 双层 | 双层 (conv + agent) | Sub-agent 粒度统计费用 |
| 版本号 | 三段式 vs 单调递增 | 单调递增 int | 简单可靠，减少比较复杂度 |

---

## 11. 代码量统计

截止 2026-06-19（实际统计）:

| 类别 | 文件数 | 代码行数 | 说明 |
|------|--------|---------|------|
| agent/ | 31 | 3,816 | Unified Master + sub-agents + tools |
| api/ | 17 | 1,292 | FastAPI routers + schemas |
| infrastructure/ | 56 | 5,860 | DB, RAG, PPT engine, LLM, config |
| 其他 (main.py 等) | 2 | 60 | 入口文件 |
| **后端合计** | **106** | **11,028** | |
| tests/ | 37 | 4,208 | pytest 单元测试 + agent 测试 |
| 前端 (Vue3) | 29 | 2,952 | views + components + stores + api |
| **项目总计** | **172** | **18,188** | |

后端文件平均 ~104 行，中位数 < 80 行。超 300 行文件 8 个，超 500 行文件 1 个（`ppt_engine/parser/base.py`）。
