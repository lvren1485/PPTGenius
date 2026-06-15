# PPTGenius 待解决问题清单

> 版本: 0.3.0 | 日期: 2026-06-15

---

## 目录

- [PPTGenius 待解决问题清单](#pptgenius-待解决问题清单)
  - [目录](#目录)
  - [1. Generator/Explore 架构分离](#1-generatorexplore-架构分离)
  - [2. 数据结构与同步](#2-数据结构与同步)
  - [3. 版本号系统重构](#3-版本号系统重构)
  - [4. 标记系统 DB 化](#4-标记系统-db-化)
  - [5. 字体与导出](#5-字体与导出)
  - [6. Middleware 统一化](#6-middleware-统一化)
  - [7. agent/common 拆分评估](#7-agentcommon-拆分评估)
  - [8. 已决策方案](#8-已决策方案)
  - [9. 数据库变更](#9-数据库变更)
  - [10. Repository 变更](#10-repository-变更)
  - [总结 —— 按优先级排序](#总结--按优先级排序)

---

## 1. Generator/Explore 架构分离

### 1.1 Generator 搜索-写入失衡

**现象**：`generator.py` 持有搜索工具 + 写入工具，LLM 陷入搜索循环不写大纲。当前 `_WRITE_HINT` 强行催促，效果不稳定。

**根因**：搜索和写入同时暴露给同一个 LLM。agent_old 的「一次搜索 + 一次输出」更稳定。

### 1.2 `_WRITE_HINT` 对 explore Agent 语义错误

**位置**：`knowledge_tools.py:22`

```python
_WRITE_HINT = "\n\n 如果已收集到足够信息，请立即调用 write_slides 工具写入内容。禁止直接输出"
```

Explore 的工具是 `read_file` + `submit_note`，没有 `write_slides`。分离工具集后此 HINT 可删除。

### 1.3 方案：搜索与生成完全分离

```
Master 收到用户消息
  │
  ├─ [1] explore_knowledge   ← 仅 Master 调用一次
  │      感知 RAG mode (user vs conversation)
  │      工具: RAG search + web search + 看 summary
  │      产出: section 划分 + file_id/chunk_id 映射
  │
  ├─ [2] write_outline_structure
  │      Master 按 explore 的 section 划分 1:1 创建
  ├─ [3] outline_section ×N  ← Generator 只写不搜
  │      传入: 对应 section 关联的 knowledge file 全文
  │      (由 explore 输出的 file_id/chunk_id 直接读 DB 拼入 prompt)
  │      可选: 额外给一次 search 能力做补充
  │      工具: write_slide + pending_slides
  │
  └─ [4] outline_evaluate
```

### 1.4 文件 Summary 统一化（入库前自动执行）

**核心原则**：Summary 在文件入库时生成，代码集中在一处，不在 API/Web fetch 中散落。

#### Decision Table

| 来源 | 文件类型 | Summary 策略 |
|------|---------|-------------|
| 用户上传 | 文档 (pdf/docx/md/txt) | LLM 采样总结 (200-500字) |
| 用户上传 | 数据 (csv/xlsx) | ≤30行 → `summary_json = null`；>30行 → 原始内容直接作为 summary（免 LLM） |
| 网络搜索 | HTML 页面 | fetch 后 LLM 总结 |

- **≤30 行的短文件不生成 summary**（原始内容本身已足够短，Explore 可直接读）
- **>30 行已存储 summary 的**：preview 仅用于摘要生成，不在 DB 中冗余存储

#### Summary 存放位置与 Explore 可见性

```
knowledge_files
  ├─ summary_json   ← LLM 摘要 / 数据文件原始内容
  └─ Explore 只看 summary_json，不直接读 chunks
```

- Explore 对 knowledge file **只看 summary**（不看 raw chunks）
- Explore 通过 `search_knowledge`（BM25）搜索时可看到匹配的 chunk 内容（仅匹配片段）
- 对 web search 结果：Explore 只看 summary，不接触原始页面全文

#### 架构决策：Summary 代码放哪里？

**问题**：Summary 需要调 LLM，不能放 infrastructure。但如果放 agent 层则散落在 API upload / web fetch 两处。

**评估 agent/common 移动到 infrastructure 的必要性**：

| 文件 | 当前层 | 是否可移到 infra | 理由 |
|------|--------|-----------------|------|
| `model_builder.py` | agent/common | **是** | LLM 工厂，纯基础设施，被所有 agent 依赖 |
| `token_middleware.py` | agent/common | **是** | Token 计数中间件，跨切面关注点 |
| `langchain_adapter.py` | agent/common | **是** | DeepSeek 协议适配，与 agent 逻辑无关 |
| `tool_sse_wrapper.py` | agent/common | **否** | SSE 流推送是 agent 层行为 |
| `agent_registry.py` | agent/common | **否** | 管理 agent 生命周期（push_sentinel 等） |
| `message_utils.py` | agent/common | 可讨论 | 消息序列化，偏基础设施 |

**方案**：将 `model_builder` + `langchain_adapter` 移到 `infrastructure/llm/`，`SummaryService` 放在 `infrastructure/rag/summary.py`。

**SummaryService 设计**：

```python
# infrastructure/rag/summary.py
class SummaryService:
    """文件摘要生成 — 使用 infrastructure/llm/ 的 LLM 工厂"""
    
    async def summarize(self, file_id: int, db: Database) -> str | None:
        """入库前自动调用。返回 None 表示不需要 summary（≤30行）"""
    
    async def summarize_web(self, url: str, text: str) -> str:
        """网页抓取后调用"""
```

**调用链**：
```
POST /api/knowledge/upload
  → km.ingest(db, path, user_id, conv_id)    # infrastructure — 现有
  → SummaryService.summarize(file_id, db)     # infrastructure — 新增

search_web → fetch_web 工具
  → WebSearchService.fetch_and_ingest(url)     # infrastructure — 现有
  → SummaryService.summarize_web(url, text)    # infrastructure — 新增
```

这样 Summary 逻辑集中在一个类中，API 和 Web fetch 都只调用 infrastructure 层接口，不违反分层。

### 1.5 知识传递链：Explore → Generator

**Explore 的能力边界**：
- RAG `search_knowledge`（BM25 搜索 chunk 全文）
- Web `search_web`（DuckDuckGo/SearXNG）
- 看 knowledge file 的 `summary_json`（不是 raw chunks）
- **输出**：结构化的 section 划分 + 每 section 对应的 file_id + chunk_id

**Explore 产出结构**：
```json
{
  "sections": [
    {
      "title": "市场背景",
      "description": "...",
      "knowledge_file_ids": [1, 3],
      "key_chunk_ids": [12, 45, 78]
    }
  ]
}
```

**Generator 接收**：根据 explore 的 `file_id` + `chunk_id`，从 DB 直接读取对应的 chunk_text，全文拼入 prompt。可选额外给一次 `search_knowledge` 做补充。

**关于 Section 创建是否下放到 Explore**：
- 如果要下放：Explore 内部调用 `write_outline_structure` → 职责扩大，接近替代 Master 的大纲创建
- 如果不下放：Master 根据 Explore 的 JSON 输出创建 sections → Master 保持编排角色
- **推荐不下放**——Explore 专注知识探索和划分建议，Master 负责执行

### 1.6 输出格式：强制结构化以消除 Retry

**问题**：当前 Generator 的 ReAct 循环中 LLM "忘了"调用 write_slide。Retry 实测 3 次仅 1 次成功——retry 不可靠。

> 三种类型： tool json, output json, output markdown. 对于 generator，因为削减了tool，可以尝试output json或者不修改，output markdown暂不考虑，太不稳定。

**方向**：让 Explore 和 Generator 输出结构化 JSON/MD，减少自由 ReAct。

**Explore**：最终输出 JSON（section 划分 + file_id/chunk_id），不依赖多轮工具调用。即使内部有搜索工具，最终产出规定为结构化 JSON。

**Generator**：直接输出 JSON 格式的 slides 内容。风险是 JSON 缺字段无法修正。折中方案——用 Markdown 结构化输出（容错性更好）：
```markdown
## slide_index=1: 标题
main_points: [...]
detailed_content: ...
recommended_ppt_format: bullet_list
---
## slide_index=2: 副标题
...
```
然后用 parser 解析 Markdown → 调 write_slide。

**目标**：一次过，不 retry。

---

## 2. 数据结构与同步

### 2.1 Outline 结构修改后 Presentation Slide 无法同步

**现象**：`modify_outline_structure` 增/删/重排 outline_slides 后，`presentation_slides` 完全不知情。如果 outline 增加了 slide，pres 侧没有对应 record；outline 删除了 slide，pres 侧存在孤儿记录。

**根因**：outline_slides 和 presentation_slides 之间没有级联同步机制，靠 `outline_slide_id` 外键但无实际同步逻辑。

**修复方向**：
- `modify_outline_structure` 执行后，自动同步 presentation_slides 结构
- 新增 `rearrange_presentation_slides` 工具，根据 outline_slides 重排 pres slides（保留已有 agent_outputs，新 slide 置为 pending）
- 删 outline slide → 标记对应 pres slide 为 `orphan` 或直接删除
- 增 outline slide → 创建 pres slide 占位 (status=pending)

### 2.2 未使用的字段

| 表 | 字段 | 状态 | 说明 |
|-----|------|------|------|
| `knowledge_files` | `web_url` | 未填写 | `fetch_web` 后应回写源 URL |
| `knowledge_files` | `summary_json` | 未使用 | 见 §1.5 |
| `outlines` | `eval_detail` | 未使用 | `outline_evaluate` 已写 `eval_score`，但 `eval_detail` 始终为 null |

**修复方向**：
- `fetch_web` 回写 `knowledge_files.web_url`
- 实现 §1.5 的 summary 流程
- `outline_evaluate` 写入 `eval_detail`（结构化评测结果数组）

### 2.3 OutlineSlide Citations 格式

**当前格式**：`[{chunk_id, knowledge_file_id, reason}]`

**问题**：`reason` 字段在 generator prompt 中要求填写但 LLM 未必填写。

**修复方向**：在 `write_slide` 工具中校验 citations，无 reason 的 citation 补默认值（如 "used in slide content"）。

---

## 3. 版本号系统重构

### 3.1 现状

| 表 | 版本字段 | 说明 |
|-----|---------|------|
| `outlines` | `version_major, version_minor, version_patch` | 三段式，语义明确但复杂 |
| `outline_snapshots` | `version` (int) | 递增整数，独立于 outline 版本 |
| `presentations` | **无** | PPT 无自身版本号 |
| `presentation_snapshots` | `version` (int) | 递增整数 |

**问题**：
1. Outline 三段式对用户无意义——用户只需要一个数字就知道「第几版」
2. Presentation 没有版本号字段，无法追踪 PPT 自身的迭代
3. Presentation 没有记录对应的 outline 版本，无法判断「大纲改过之后 PPT 是否需要重新生成」
4. Snapshot 的 version 和 outline 的 version 是两套独立递增，逻辑混乱

### 3.2 方案

**Outline 版本**：删除 `version_major/minor/patch`，改为单个 `version: int`（默认 1）。
每次修改 outline 时自增（`write_outline_structure`、`modify_outline_structure`、`outline_section` 完成时）。

**Presentation 版本**：
- 新增 `version: int`——在同一个 outline version 下的 PPT 迭代次数（默认 1）
- 新增 `outline_version: int`——记录生成时对应的大纲版本号

**Presentation 版本生命周期**：
```
outline id=1, version=1
  ├─ presentation version=1 (outline_version=1)  ← 首次生成
  ├─ presentation version=2 (outline_version=1)  ← 用户微调后重新生成
  └─ presentation version=3 (outline_version=1)  ← 换了 style 重新生成

outline id=1, version=2   ← 大纲修改，version 自增
  ├─ presentation version=1 (outline_version=2)  ← 重新开始计数
  └─ presentation version=2 (outline_version=2)
```

即 outline version 每变一次，presentation version 从 1 开始重新计数。

**Snapshot 版本**：
- `outline_snapshots.version` — 直接记录 `outline.version`
- `presentation_snapshots.version` — 不独立递增，记录 `{outline_version, presentation_version}` 组合

**过期判断**：
- `presentation.outline_version < outline.version` → PPT 对应旧版大纲，需重新生成
- `presentation.outline_version == outline.version` → 同步，可编辑或导出

---

## 4. 标记系统 DB 化

### 4.1 现状：标题嵌入标记

**位置**：`generator.py:26` — `_FLAGS = ("待合并", "待分割", "待填充", "新页", "待修改")`

**做法**：`modify_outline_structure` 在 slide title 中嵌入 flag 文字（如「待修改 — 旧标题」），generator 通过 `_detect_flag()` 解析。

**问题**：
1. 标题被污染——用户看到的 slide 标题带「待修改」前缀
2. 标记不可被数据库查询（无法 `WHERE flag = '待修改'`）
3. 删除标记需要修改标题（又触发一次标题变更）
4. Presentation slide 侧完全没有感知 flag 变化

### 4.2 方案

**扩展 `outline_slides.status` 值域**（不新增列）：
- `pending` / `completed` — 生命周期
- `merge` / `split` / `fill` / `new` / `modify` — 操作标记

**检测逻辑**：Generator 检查 section 内是否有 `status != "completed"` 的 slide，而非解析 title 文字。

**级联到 Presentation**：
- `outline_slides.status` 变更时，对应 `presentation_slides` 标记为 `status = "pending"`（需重新生成）
- 在 `slides_content` 生成完成后自动清除（status → `"completed"`）

**修改流程**：
- `modify_outline_structure` 直接设 `outline_slides.status`（而非污染 title）
- 见 §9.2 数据库变更明细

### 4.3 Generator 修改流程增强

**当前修改流程**：
```
modify_outline_structure → flag field → outline_section (generator) → 检查 flag → 重写 → 清除 flag
```

**新增：Rearrange Presentation Slides 工具**

**工具名**：`rearrange_presentation_slides`

**功能**：根据 outline_slides 的当前结构重排 presentation_slides。
- 匹配 key：`outline_slide_id`
- 新增的 outline_slide → 创建 presentation_slide 占位 (status=pending)
- 删除的 outline_slide → 标记 presentation_slide 为 `orphan` 或删除
- slide_index 变更 → 更新 presentation_slide.slide_index

**调用时机**：`modify_outline_structure` 执行后自动调用，或 Master 显式调用。

---

## 5. 字体与导出

### 5.1 字体问题

**现象**（来自 agent_old 实测）：
- 导出 .pptx 后在 PowerPoint 中打开，字体显示为微软默认字体（等线/宋体）
- 无法通过格式刷复制字体样式
- 没有提供字体选择选项（style 中有 `fonts_json` 但未实际生效）

**根因**：python-pptx 字体设置链路断裂——
1. `fonts_json` 中的字体名未正确写入 XML `<a:rPr>` 的 `latin` / `ea` / `cs` 属性
2. 可能写了字体名但 PowerPoint 本地无该字体 → 回退到默认字体
3. 格式刷失效说明字体信息根本没有写入元素属性

**修复方向**：
- 检查 parser 中字体写入逻辑（`latin` = 西文、`ea` = 东亚、`cs` = 复杂文字）
- 提供可用的中文字体列表（思源黑体、微软雅黑、等线、宋体）
- Style 选择时预览字体，确保 fallback 链正确

### 5.2 导出机制

**原则**：导出应基于 **snapshot**，而非直接读 outline/presentation 当前状态。

- `outline_slides` 和 `presentation_slides` 是 LLM 的 **工作区**（可被后续修改覆盖）
- `snapshots` 是 **不可变的历史记录**（用户看到的每个版本）

**导出流程**：
```
用户点击导出
  │
  ├─ outline 导出  → 从 outline_snapshots (version=N) 读取
  ├─ PPT 导出      → 从 presentation_snapshots (version=N) 读取
  └─ 当前/最新版本 → 可能已在 snapshot 中（Master 退出时自动创建）
                     也可能需要即时 assembly（尚未 snapshot 的情况）
```

---

## 6. Middleware 统一化

### 6.1 当前：三层各自实现，互不统一

Master 和子 Agent 的工具调用有三个横切关注点，目前各自实现：

| 关注点 | 当前实现 | 位置 |
|--------|---------|------|
| **SSE 推送** | `wrap_tool_with_sse(fn)` 装饰器，每个 tool maker 手动包装 | `agent/common/tool_sse_wrapper.py` |
| **Token 计数** | `TokenCountingMiddleware.after_model` — LLM 层面计数 | `agent/common/token_middleware.py` |
| **消息持久化** | `master.py::_persist_tool_messages` — Agent 结束后批量遍历写入 | `agent/master.py` |

**问题**：
1. SSE 包装散落在 ~10 个 tool maker 中（`make_get_outline`、`make_write_outline_structure`…），每个都要 `tool(wrap_tool_with_sse(fn))`
2. 消息持久化是「事后批量」——Agent 结束后遍历 `result["messages"]` 写入。如果中间 crash，全部丢失
3. `wrap_tool_with_sse` 不是标准 LangChain 中间件，无法与其他中间件编排执行顺序

### 6.2 方案：三个 LangChain 原生中间件，统一注册

```
agent = create_agent(
    model=llm,
    tools=tools,
    middleware=[
        PersistToolMiddleware(db, conv_id),   # ③ 最外层：逐步持久化
        SSEToolMiddleware(),                   # ② 中层：SSE 推送
        TokenCountingMiddleware(conv_id, aid), # ① 内层：Token 计数
    ],
)
```

中间件按**注册反序**执行（last → first），hook 返回后按正序恢复。以一次 `wrap_tool_call` 为例：

```
PersistToolMiddleware.wrap_tool_call 进入    ← ③ 先：写 tool_call 到 DB
  SSEToolMiddleware.wrap_tool_call 进入      ← ② 次：发 tool_start SSE
    TokenCountingMiddleware (无 wrap_tool_call)
      handler(request)                       ← 工具真正执行
  SSEToolMiddleware.wrap_tool_call 返回      ← ② 发 tool_end/tool_error SSE
PersistToolMiddleware.wrap_tool_call 返回    ← ③ 写 tool_result 到 DB
```

#### 中间件 A：`PersistToolMiddleware`

```python
from langchain.agents.middleware import AgentMiddleware
from langchain.tools.tool_node import ToolCallRequest
from langchain.messages import ToolMessage
from langgraph.types import Command
from collections.abc import Callable

class PersistToolMiddleware(AgentMiddleware):
    """每调一个工具立即落库 tool_call + tool_result，不等待 Agent 结束。"""

    def __init__(self, db: Database, conversation_id: int):
        super().__init__()
        self._db = db
        self._conversation_id = conversation_id
        self._ctypes = _TOOL_CTYPE  # 复用 master.py 的映射

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        tc_name = request.tool_call["name"]
        tc_args = request.tool_call["args"]
        tc_id = request.tool_call["id"]
        ctype = self._ctypes.get(tc_name, "tool_call")

        # ① 持久化 tool_call
        self._db.create_message(
            conversation_id=self._conversation_id,
            role="tool_call",
            content=tc_args.get("query", "") or "",
            content_type=ctype,
            metadata_json={"tool_name": tc_name, "args": tc_args, "tool_call_id": tc_id},
        )

        # ② 执行工具
        result = handler(request)

        # ③ 持久化 tool_result
        content = str(result.content) if hasattr(result, "content") else str(result)
        msg = self._db.create_message(
            conversation_id=self._conversation_id,
            role="tool_result",
            content=content,
            content_type=ctype,
            metadata_json={"tool_name": tc_name, "tool_call_id": tc_id},
        )

        # ④ 子 Agent tool：汇总 token cost（替代 master.py 的 pop_until_sentinel）
        if ctype in _SUB_AGENT_TOOLS:
            agent_ids = pop_until_sentinel(self._conversation_id)
            if agent_ids:
                summed = {}
                total_cost = 0.0
                for aid in agent_ids:
                    tc = TokenCounter.get_agent(aid)
                    if tc:
                        for k, v in tc.to_json().items():
                            summed[k] = summed.get(k, 0) + v
                        total_cost += tc.snapshot()["estimated_cost_cny"]
                self._db.set_message_cost(msg.id,
                    token_cost_json=summed, estimated_cost=total_cost)

        return result
```

#### 中间件 B：`SSEToolMiddleware`

```python
class SSEToolMiddleware(AgentMiddleware):
    """替掉 wrap_tool_with_sse 装饰器，对所有 tool 自动生效。"""

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        writer = _get_sse_writer()
        tc_name = request.tool_call["name"]
        tc_args = request.tool_call["args"]

        writer({"type": "tool_start", "tool": tc_name, "args": _safe_args(tc_args)})
        try:
            result = handler(request)
        except Exception as exc:
            writer({"type": "tool_error", "tool": tc_name, "error": str(exc)})
            raise
        result_len = len(str(result.content)) if hasattr(result, "content") else 0
        writer({"type": "tool_end", "tool": tc_name, "result_len": result_len})
        return result
```

#### 中间件 C：`TokenCountingMiddleware`（不动）

只保留 `after_model` hook，继续累加 token 用量。无需 `wrap_tool_call`。

### 6.3 删除项

| 删除 | 原因 |
|------|------|
| `agent/common/tool_sse_wrapper.py` | 被 `SSEToolMiddleware` 替代 |
| 所有 `make_xxx` 中的 `wrap_tool_with_sse(fn)` 包装 | ~10 处，不再需要 |
| `master.py::_persist_tool_messages()` | 被 `PersistToolMiddleware` 替代 |

### 6.4 改动量

| 操作 | 文件数 | 行数 |
|------|--------|------|
| 新增 `PersistToolMiddleware` | 1 | ~60 |
| 新增 `SSEToolMiddleware` | 1 | ~25 |
| 修改各 agent 的 `create_agent` 加 middleware | ~7 | 各 1-2 行 |
| 删除 `wrap_tool_with_sse` 包装 | ~10 | 各 1 行 |
| 删除 `master.py::_persist_tool_messages` | 1 | ~70 行（净删除） |
| 删除 `tool_sse_wrapper.py` | 1 | ~55 行（整文件） |

> 净效果：新增 ~85 行，删除 ~135 行。净减少 ~50 行。结构更清晰。

### 6.5 `_get_sse_writer` 可用性

`get_stream_writer()` 基于 LangGraph context var，在整个 agent invocation 链中可用。中间件的 `wrap_tool_call` 在同一 context 中执行，可直接调用。

---

## 7. agent/common 拆分评估

### 8.1 现状

`agent/common/` 混合了基础设施和 agent 层关注点：

```
agent/common/
├── langchain_adapter.py   (~90)  协议适配 → 偏 infra
├── token_middleware.py     (~60)  Token 计数 → 偏 infra
├── model_builder.py        (~80)  LLM 工厂 → 偏 infra
├── tool_sse_wrapper.py     (~55)  → §6 删除，被 SSEToolMiddleware 替代
├── agent_registry.py       (~80)  Agent 生命周期 → agent 层
└── message_utils.py        (~50)  消息序列化 → 可 infra
```

### 8.2 拆分方案

```
infrastructure/llm/          ← 新建
├── adapter.py               ← 原 langchain_adapter.py
├── factory.py               ← 原 model_builder.py
└── token_middleware.py      ← 原 token_middleware.py

infrastructure/middleware/    ← 新建（或放在 agent/common/middleware/）
├── persist_tool.py          ← PersistToolMiddleware
└── sse_tool.py              ← SSEToolMiddleware

agent/common/
├── agent_registry.py        ← 不动
└── message_utils.py         ← 不动（或移到 infra）
```

### 8.3 影响评估

| 变更 | 影响文件数 | 风险 |
|------|-----------|------|
| `model_builder` 移到 infra | ~10（所有 agent 的 import） | 低——纯 import 路径变更 |
| `langchain_adapter` 移到 infra | ~3 | 低 |
| `token_middleware` 移到 infra | ~3 | 低 |
| Middleware 三合一 | ~15 | 中——涉及所有 agent 的工具注册方式 |
| SummaryService 新建 | 2-3 | 低——新增代码 |

**建议**：Middleware 统一化 + agent/common 拆分 + Summary 一起做，集中一次 import 变更。

---

## 8. 已决策方案

> 以下为已确认的架构决策，后续实施依据。

### 8.1 Section 创建：Master 负责（选 A）

Explore 产出 section 建议 JSON → Master 调 `write_outline_structure`。Explore 专注知识探索，不越权创建结构。

### 8.2 Generator 知识传递：直接传全文（选 A）

Generator 不再持有任何搜索工具。Explore 产出的 `file_id + chunk_id` → `outline_section` 工具内部从 DB 读取 chunk_text，全文拼入 Generator prompt。零查询、简单可靠。

### 8.3 输出格式

| Agent | 输出格式 | 说明 |
|-------|---------|------|
| Explore | JSON（先试） | 工具多但输出单一，直接 output JSON；如果 LLM 不配合再改 MD |
| Generator | 不改变 | 已去搜索工具，负担大幅减轻，保持现有 write_slide 工具模式 |

### 8.4 Pres Slide 同步：级联删除 + Snapshot 恢复（选 A）

- Outline slide 删除 → 对应 pres slide 级联删除
- 如需恢复：从 snapshot 中重建
- 不保留 orphan pres slide

### 8.5 Flag：复用 status 字段（选 B）

扩展 `outline_slides.status` 值域：
- `pending` / `completed`（生命周期）
- `merge` / `split` / `fill` / `new` / `modify`（操作标记）

不新增 `flag` 列。Generator 检测逻辑：检查 section 内是否有 `status != "completed"` 的 slide。

### 8.6 Explore 存储与 Citation

**全量 Explore**：Explore 结果写入 DB（作为下次 Explore 的前置上下文 + 崩溃恢复）。Citation 在内存中传递，不落 DB。

**增量 Explore**：用户后续上传新文件或修改 section → 全量 re-explore。Citation 随 explore 结果刷新。已生成的 slide content_json 不受影响。

**Generator 的输入 prompt** = 三部分拼接：
1. 上一次 Explore 的完整结果（从 DB/内存读取）
2. 当前用户 query
3. 对应 section 的 knowledge file 全文（按 file_id + chunk_id 从 DB 读取）

### 8.7 Document Message 持久化

（待实施时确定具体写入点，原则：Master 在 snapshot 阶段统一写入）

---

## 9. 数据库变更

> 汇总全文所有需要修改 schema 的条目。已存在但未填充的字段不在此列（见 §2.2），仅列需要 ALTER 或新增的字段。

### 9.1 Schema 变更总览

| # | 表 | 操作 | 字段 | 类型 | 说明 |
|----|-----|------|------|------|------|
| 1 | `outlines` | **删** | `version_major`, `version_minor`, `version_patch` | INTEGER | 三段式 → 单个 version |
| 2 | `outlines` | **增** | `version` | INTEGER NOT NULL DEFAULT 1 | 单调递增，每次修改 outline 后自增 |
| 3 | `outlines` | **改** | `eval_detail` | JSON | 已有字段，需填充评测详情 |
| 4 | `outlines` | **增** | `explore_result_json` | JSON | Explore 完整输出，下次 Explore 前置上下文 |
| 5 | `presentations` | **增** | `version` | INTEGER NOT NULL DEFAULT 1 | 同一 outline_version 下的迭代次数 |
| 6 | `presentations` | **增** | `outline_version` | INTEGER NOT NULL DEFAULT 0 | 生成时对应的大纲版本；0 表示未关联 |
| 7 | `outline_slides` | **改** | `status` | VARCHAR(32) | 值域扩展：p/completed/merge/split/fill/new/modify |
| 8 | `knowledge_files` | **改** | `summary_json` | JSON | 已有字段，存储纯文本摘要（非结构化 JSON） |
| 9 | `knowledge_files` | **改** | `web_url` | VARCHAR(2048) | 已有字段，fetch_web 回写源 URL |

### 9.2 字段详细说明

#### 9.2.1 `outlines.version` — 替代三段式

```sql
ALTER TABLE outlines DROP COLUMN version_major;
ALTER TABLE outlines DROP COLUMN version_minor;
ALTER TABLE outlines DROP COLUMN version_patch;
ALTER TABLE outlines ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
```

自增时机：`write_outline_structure`、`modify_outline_structure`、`outline_section` 全部完成后（snapshot 前）。

#### 9.2.2 `outlines.explore_result_json` — Explore 缓存

```sql
ALTER TABLE outlines ADD COLUMN explore_result_json JSON;
```

结构：
```json
{
  "run_at": "2026-06-15T10:00:00",
  "mode": "full",
  "sections": [
    {
      "title": "市场背景",
      "description": "...",
      "knowledge_file_ids": [1, 3],
      "key_chunk_ids": [12, 45, 78],
      "summary": "..."
    } 
  ]
}
```

全量 re-explore 时覆盖。Generator prompt 拼接时从此读取。

#### 9.2.3 `presentations.version` + `outline_version`

```sql
ALTER TABLE presentations ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE presentations ADD COLUMN outline_version INTEGER NOT NULL DEFAULT 0;
```

版本关系（见 §3.2）：outline.version 每变一次，presentation.version 从 1 重新计数。

#### 9.2.4 `outline_slides.status` — 值域扩展

```sql
-- 无需 ALTER，仅扩展 CHECK 约束或应用层校验
-- 新值域: pending | completed | merge | split | fill | new | modify
```

#### 9.2.5 `knowledge_files.summary_json` — 语义变更

从「结构化 JSON 摘要」改为「纯文本摘要字符串」存储。应用层兼容两种格式读取。

```json
// 旧格式（已废弃）
{"topics": [...], "key_data": [...], "suggested_sections": [...]}

// 新格式 — 纯文本
"[file_id=3] [name=AI白皮书2024.pdf] [type=pdf]\n## 摘要\n本文探讨...（200-500字）"
```

### 9.3 完整 DDL

```sql
-- outlines: 版本号 + Explore 缓存
ALTER TABLE outlines DROP COLUMN IF EXISTS version_major;
ALTER TABLE outlines DROP COLUMN IF EXISTS version_minor;
ALTER TABLE outlines DROP COLUMN IF EXISTS version_patch;
ALTER TABLE outlines ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE outlines ADD COLUMN IF NOT EXISTS explore_result_json JSON;

-- presentations: 自身版本 + 对应大纲版本
ALTER TABLE presentations ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE presentations ADD COLUMN IF NOT EXISTS outline_version INTEGER NOT NULL DEFAULT 0;
```

---

## 10. Repository 变更

> 对应 §9 数据库变更，需要修改的 repository 文件。

### 10.1 `infrastructure/db/repository/outline.py`

| 方法 | 变更 |
|------|------|
| `increase_outline_version(outline_id, type)` | **重写**：删除 `type` 参数，改为 `outline.version += 1` |
| `update_outline_eval(outline_id, score, detail)` | **不改**（已存在），确保调用方传入 `detail` |
| `get_outline(outline_id)` → `version` 字段 | **不改**（ORM 自动映射新列） |
| `create_outline(...)` | **不改**（`version` 有 DEFAULT 1） |
| `set_explore_result(outline_id, result_json)` | **新增**：写 `explore_result_json` |
| `get_explore_result(outline_id)` | **新增**：读 `explore_result_json` |

`increase_outline_version` 新签名：

```python
async def increase_outline_version(db: AsyncSession, outline_id: int) -> bool:
    outline = await db.get(Outline, outline_id)
    if outline is None or outline.status == "deleted":
        return False
    outline.version += 1
    await db.commit()
    return True
```

### 10.2 `infrastructure/db/repository/presentation.py`

| 方法 | 变更 |
|------|------|
| `create_presentation(...)` | **改**：接收 `outline_version: int` 参数，写入新列 |
| `increment_presentation_version(pres_id)` | **新增**：`pres.version += 1` |

### 10.3 `infrastructure/db/repository/outline_slide.py`

| 方法 | 变更 |
|------|------|
| `update_outline_slide_status(slide_id, status)` | **不改**（已存在），调用方传入新值域 |
| 删除 `_detect_flag()` 相关逻辑 | **agent 层**（`outline/prompts.py`），非 repo |

### 10.4 `infrastructure/db/repository/knowledge_file.py`

| 方法 | 变更 |
|------|------|
| `set_summary(file_id, summary_text)` | **新增**：写 `summary_json`（存纯文本） |
| `set_web_url(file_id, url)` | **新增**：写 `web_url` |

### 10.5 `infrastructure/db/database.py` (facade)

| 方法 | 变更 |
|------|------|
| `increase_outline_version(outline_id, type)` | **改签名**：删 `type` 参数 |
| `set_explore_result(outline_id, result)` | **新增**：透传 repo |
| `get_explore_result(outline_id)` | **新增**：透传 repo |
| `increment_presentation_version(pres_id)` | **新增**：透传 repo |
| `set_knowledge_file_summary(file_id, text)` | **新增**：透传 repo |
| `set_knowledge_file_web_url(file_id, url)` | **新增**：透传 repo |
| `set_chunk_token_count(chunk_id, count)` | **新增**：透传 repo |

### 10.6 调用方变更

| 文件 | 变更 |
|------|------|
| `agent/master.py` | `increase_outline_version(id, "major")` → `increase_outline_version(id)` |
| `agent/tools/outline_section.py` | 同上 |
| `agent/tools/outline_evaluate.py` | `update_outline_eval` 时传入 `detail` 参数 |
| `agent/tools/slides_content.py` | 创建 presentation 时传入 `outline_version` |
| `agent/outline/knowledge_tools.py` | `fetch_web` 后调 `set_web_url` |
| `agent/tools/explore_knowledge.py` | Explore 完成后调 `set_explore_result` |

---

## 总结 —— 按优先级排序

| 优先级 | 条目 | 影响面 |
|--------|------|--------|
| **P0** | §1.3 Generator/Explore 分离 + Generator 去搜索工具 | 解决核心稳定性问题 |
| **P0** | §1.6 强制结构化输出 + 消除 Retry | 稳定性兜底 |
| **P0** | §6 Middleware 统一化（Persist + SSE + Token）| 逐步持久化 + 删 tool_sse_wrapper + 删 _persist_tool_messages |
| **P1** | §1.4 Summary 统一化（入库前） | 知识获取基础设施 |
| **P1** | §7 agent/common 拆分 | 分层清理，为 Summary 铺路 |
| **P1** | §4 标记系统 DB 化 | 数据完整性 |
| **P1** | §3 版本号重构 | 系统设计一致性 |
| **P1** | §2.1 Pres Slide 同步 + Rearrange 工具 | 大纲/PPT 联动 |
| **P2** | §1.5 知识传递链（Explore → Generator） | 信息不丢失 |
| **P2** | §2.2 未使用字段补全 | 数据完整 |
| **P2** | §5.1 字体修复 | PPT 产出质量 |
| **P3** | §5.2 导出基于 Snapshot | 版本追溯 |
| **P3** | §8.7 Document Message 持久化 | 细节待定 |
