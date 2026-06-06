# PPTGenius 代码规范评审报告 — Milestone 2

**评审日期：** 2026-06-07
**评审人：** 左凌旭（开发者自审）
**评审范围：** API 层、Agent 层、Infrastructure 层核心模块
**评审依据：** PEP 8 + 项目内部约定

---

## 一、评审概况

| 维度 | 权重 | 得分 | 说明 |
|------|------|------|------|
| 命名规范 | 25% | 4.5 | PEP 8 近完全合规 |
| 代码风格与格式 | 20% | 4.0 | 导入排序、缩进规范，少数长行待优化 |
| 注释与文档 | 20% | 3.5 | 模块文档覆盖率 90%，私有函数文档偏少 |
| 类型标注完整性 | 15% | 4.0 | 参数/返回值近乎全覆盖 |
| 代码结构与模块化 | 20% | 4.0 | 三层架构严格分离，最大文件 649 行 |
| **综合评分** | | **4.03 / 5** | |

---

## 二、命名规范 (4.5/5)

整体严格遵守 PEP 8：

- **模块名** `snake_case`：`chat.py`, `langchain_adapter.py`
- **类名** `PascalCase`：`CoordinatorDecision`, `BM25Manager`, `PPTState`
- **函数/变量** `snake_case`：`run_coordinator()`, `conversation_id`
- **常量** `UPPER_CASE`：`_MAX_RETRY_ROUNDS`, `SLIDE_BOUNDS`
- **私有成员** `_前缀`：`_classify_intent()`, `_sse()`
- **布尔变量** `is_/has_`：`has_outline`, `is_modify`, `has_error`

**待改进：** 少量缩写变量（`pres`→`presentation`，`conv`→`conversation`）在公开 API 上下文中可读性略差。

---

## 三、代码风格与格式 (4.0/5)

**合规项：**
- 导入顺序规范（标准库 → 第三方 → 本地），分组间保留空行
- 4 空格缩进统一，空行使用符合 PEP 8
- `from __future__ import annotations` 全文一致
- f-string 优先于 `.format()`

**待改进：**
- `coordinator.py` 中部分 SSE 内联字典超 120 字符，建议提取为命名辅助函数
- 尾随逗号不一致，建议运行 `ruff format` 全局修复
- `───` 分节注释宽度不统一，建议固定为 78 字符

---

## 四、注释与文档 (3.5/5)

**覆盖率：**
- 模块文档字符串：9/10（90%），`db/models.py` 缺少 ER 概览
- 公有函数文档字符串：~18/25（72%），核心入口函数质量良好
- 私有函数文档字符串：~5/15（33%），`_create_presentation_node`、`_assembly_node` 缺少说明

**典型问题：**
- `agent/outline/graph.py` 含 ASCII 流程图，为最佳范例
- 行内注释约 60% 解释 WHY（设计意图），40% 仅复述 WHAT，建议提高前者比例
- 无 TODO/FIXME/HACK 遗留标记（干净）

---

## 五、类型标注与代码结构 (4.0/5)

**类型标注：**
- 函数参数与返回值标注接近 100%，包括 `AsyncGenerator[str, None]`
- SQLAlchemy 2.0 `Mapped[]`、Pydantic 泛型 `ApiResponse[T]` 使用规范
- 待改进：`generate_ppt()` 中 `data: dict[str, Any]` 建议替换为 `TypedDict`

**架构合规：**
- API → Agent → Infrastructure 三层严格分离，Infrastructure 零向上引用
- API 层仅通过 `run_coordinator` 公开入口调用 Agent

**模块化问题：**
- `coordinator.py` 649 行，建议提取 SSE 辅助函数至独立模块
- **P0 问题**：`coordinator.py` 中 `_rationale_store: list[str] = []` 为模块级可变列表，非线程安全且跨请求存活，需重构为 LangGraph state 传递
- 已废弃代码（`phase2_sub_agent/`、`phase2_freedom/`）标记清晰

---

## 六、改进优先级

| 优先级 | 问题 | 文件 | 工作量 |
|--------|------|------|--------|
| **P0** | 消除模块级可变状态 `_rationale_store` | `coordinator.py` | 小 |
| **P1** | 补充 `_create_presentation_node`、`_assembly_node` 文档 | `ppt/graph.py` | 中 |
| **P1** | 补充 `db/models.py` 模块文档（ER 图概览） | `models.py` | 中 |
| **P2** | 日志消息统一为英文 | 多文件 | 中 |
| **P3** | 运行 `ruff format` 统一格式 | 全局 | 小 |

---

## 七、评审结论

PPTGenius 代码库在命名规范和架构分离方面表现优秀，PEP 8 近完全合规，三层架构零循环依赖。主要短板为：部分复杂函数缺少文档字符串、一处模块级可变状态需重构、日志中英文混用。以上问题不影响 Milestone 2 功能交付，建议在最终提交前完成 P0、P1 项整改。