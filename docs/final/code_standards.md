# PPTGenius 代码规范与整洁度审查

> 版本: 0.3.0 | 日期: 2026-06-18

---

## 目录

- [PPTGenius 代码规范与整洁度审查](#pptgenius-代码规范与整洁度审查)
  - [目录](#目录)
  - [1. 文件组织规范](#1-文件组织规范)
  - [2. 命名规范](#2-命名规范)
  - [3. 架构模式规范](#3-架构模式规范)
  - [4. 数据库操作规范](#4-数据库操作规范)
  - [5. Agent 开发规范](#5-agent-开发规范)
  - [6. 代码整洁度审查结果](#6-代码整洁度审查结果)
  - [7. 已知技术债](#7-已知技术债)

---

## 1. 文件组织规范

### 1.1 行数限制

| 阈值 | 行为 |
|------|------|
| ≤ 300 行 | 正常 |
| 300-500 行 | 审视是否可拆分，但不强制 |
| > 500 行 | 必须拆分 |
| 单函数 ≤ 60 行 | 超过则提取子函数 |

**例外**: Pydantic schema 文件 (`api/schemas.py`) 因为是纯数据定义，行数限制可放宽至 500 行。

### 1.2 目录结构

```
src/pptgenius/
├── agent/           # Agent 层（Master + sub-agents + tools）
│   ├── common/      # 共享：middleware, agent_registry, sse_context
│   ├── tools/       # Master 的所有工具
│   ├── outline/     # Outline 子 agent（explore, generator）
│   └── ppt/         # PPT 子 agent（slide_agent, style_agent）
├── api/             # FastAPI 路由（一个模块一个文件）
├── infrastructure/  # 基础设施（不依赖 agent 层）
│   ├── config/      # 配置加载
│   ├── db/          # ORM models + repository
│   ├── llm/         # LLM factory + adapter
│   ├── rag/         # BM25 + web_search + parser
│   ├── ppt_engine/  # PPT 渲染 + validator + parser
│   ├── workspace/   # 文件管理
│   └── utils/       # 日志 + token counter
└── resources/       # 静态资源（prompts, styles, fonts）
```

**禁止**: 在 `src/` 或 `pptgenius/` 下新建未在 `improvement.md` 中列出的目录或文件。

### 1.3 静态资源

- Prompt 模板放在 `resources/prompts/` 下
- 代码中通过 `RESOURCES_DIR` 引用，禁止硬编码路径
- Style 数据（配色、字号）放在 `resources/styles/` 下

---

## 2. 命名规范

### 2.1 文件命名

| 场景 | 格式 | 示例 |
|------|------|------|
| Python 模块 | snake_case | `slide_agent.py`, `knowledge_tools.py` |
| Prompt 模板 | snake_case.md | `content_agent_system.md` |
| Style JSON | snake_case.json | `ocean_blue.json` |
| 测试文件 | `test_` 前缀 | `test_spatial_check.py` |

### 2.2 代码命名

| 场景 | 格式 | 示例 |
|------|------|------|
| 函数 | snake_case | `build_user_prompt()` |
| 类 | PascalCase | `PersistToolMiddleware` |
| 常量 | UPPER_SNAKE | `_MAX_RETRIES = 3` |
| 模块级私有 | `_` 前缀 | `_log`, `_check_spatial` |
| DB repository 函数 | 动词开头 | `get_`, `create_`, `update_`, `set_`, `soft_delete_`, `list_` |
| Tool factory | `make_` 前缀 | `make_slides_content()` |
| Tool 内部实现 | `_` 前缀 | `_slides_content()` |

### 2.3 content_type 值域

Master 工具的 `content_type` ≤ 32 字符，在 `master.py::_TOOL_CTYPE` 集中定义：

```python
_TOOL_CTYPE = {
    "slides_content": "slides_content",
    "modify_slides_content": "mod_slides",
    ...
}
```

新增工具必须在此注册映射。

---

## 3. 架构模式规范

### 3.1 依赖方向

```
api → agent → infrastructure
         ↓
    infrastructure (不依赖 agent)
```

禁止 infrastructure 反向依赖 agent。唯一的例外是 `infrastructure/export_service.py` 导入 ppt_engine。

### 3.2 Repository 模式

- 每个表一个 repository 文件（`repository/outline.py`, `repository/ppt.py`）
- Repository 函数接收 `AsyncSession` 作为第一个参数
- `Database` 类作为 facade，委托给 repository 函数
- 查询函数必须排除 soft-deleted 行（`.where(status != "deleted")`）

### 3.3 Tool Factory 模式

Master 工具通过 factory 函数创建，闭包注入 `db` 和 `conversation_id`：

```python
def make_xxx(db: Database, conversation_id: int) -> Callable:
    async def _xxx(...) -> str:
        ...
    return tool(_xxx)
```

### 3.4 子 Agent 三段式调用

```python
push_sentinel(conversation_id)          # ① 标记子 Agent 批次开始
result = await run_sub_agent(...)       # ② 运行子 Agent
# master.py 持久化时 pop_until_sentinel → 汇总 token cost
```

---

## 4. 数据库操作规范

### 4.1 Soft Delete

- 设置 `status = "deleted"`
- OutlineSlide: 同时设置 `slide_index = -slide.id`（避免唯一约束冲突）
- PresentationSlide: 仅设 status（无唯一约束，靠查询过滤）
- 所有查询函数必须排除 `status = "deleted"` 的行

### 4.2 Reindex 两步法

因为存在 `UNIQUE KEY (outline_id, slide_index)` 约束，批量更新 index 需要两步：

```python
# Pass 1: 全部设为负数 (-id) 避免碰撞
# Pass 2: 设为最终值
```

PresentationSlide 无唯一约束但沿用同样模式保持一致性。

### 4.3 Cascade 级联状态

`_cascade_pres_status` 在修改 outline 时同步标记 presentation_slide 状态：
- `o_modified_deleted`: rearrange 时 soft-delete
- `o_modified_modify`: 内容 agent 读取后重新生成
- `o_modified_split` / `o_modified_merge`: 需要内容重新生成

**注意**: `_cascade_pres_status` 不自行 commit，依赖后续操作的 commit 一并提交。

---

## 5. Agent 开发规范

### 5.1 新增 Master 工具 Checklist

1. 在 `_TOOL_CTYPE` 添加 `"tool_name" → "content_type"` 映射
2. 如果是子 Agent 工具，在 `_SUB_AGENT_TOOLS` 添加其 `content_type`
3. 在 `_assemble_tools()` 调用 `make_xxx(db, conversation_id)`
4. 子 Agent 工具必须在内部调用 `push_sentinel(conversation_id)`

### 5.2 Prompt 管理

- System prompt 和 User prompt 分离为独立 `.md` 文件
- 通过 `RESOURCES_DIR / "prompts" / "xxx.md"` 加载
- Prompt 中的变量用 `{variable_name}` 占位，在代码中 `.format()` 填充
- 禁止在 Python 代码中写超过 3 行的 prompt 字符串

### 5.3 Slide Agent 元素校验

`submit_element` 必须经过以下检查链：
1. `validate_elements()` — JSON schema 校验
2. `check_decor()` — 装饰风格冲突检查
3. `check_element()` — 空间检查（越界、重叠、溢出）

校验不通过时返回错误信息让 LLM 修正，而非静默跳过。

---

## 6. 代码整洁度审查结果

### 6.1 超限文件

| 文件 | 行数 | 状态 | 建议 |
|------|------|------|------|
| `infrastructure/ppt_engine/parser/base.py` | 501 | 需拆分 | 提取公共渲染函数到独立模块 |
| `agent/master.py` | 490 | 接近阈值 | 工具组装部分可提取 |
| `agent/tools/structure.py` | 471 | 接近阈值 | 每个工具本身不大，整体可接受 |
| `infrastructure/ppt_engine/parser/styles.py` | 433 | 接近阈值 | 数据映射为主，可接受 |

### 6.2 已修复的问题

| 问题 | 文件 | 修复 |
|------|------|------|
| `_get_slide` 未过滤 deleted | `repository/ppt.py` | 添加 `status != "deleted"` |
| `update_slides_style` 波及 deleted 行 | `repository/ppt.py` | 添加 `status != "deleted"` |
| `query_section` 前缀与模板冲突 | `slide_prompts.py` | 去除 `## ⚡` 前缀 |
| 重叠警告缺少元素类型信息 | `spatial_check.py` | 添加 `_el_label()` helper |

### 6.3 代码风格一致性

**良好实践**:
- Repository 层命名统一 (`get_`, `create_`, `update_`, `set_`, `soft_delete_`, `list_`)
- Tool factory 模式统一 (`make_xxx` → `_xxx` → `tool(_xxx)`)
- Logger 统一使用 `get_logger("pptgenius.module.name")`
- 闭包注入 `db` + `conversation_id`，避免全局状态

**需改进**:
- `structure.py` 中 `_cascade_pres_status` 使用 `db.db.execute` 绕过 facade
- 部分 repository 函数缺少 soft-delete 过滤（已修复）

---

## 7. 已知技术债

| 优先级 | 债务 | 影响 | 建议 |
|--------|------|------|------|
| P0 | `ppt_engine/parser/base.py` 超 500 行 | 难以维护 | 拆分公共渲染逻辑 |
| P1 | `master.py` 490 行接近阈值 | 后续新增工具会突破 | 工具组装提取到 `tools/__init__.py` |
| P2 | `_cascade_pres_status` 绕过 Database facade | 架构一致性 | 封装为 Database 方法 |
| P2 | 无 `(presentation_id, slide_index)` 唯一约束 | 潜在重复 slide_index | 评估是否可加 UNIQUE KEY |
| P3 | `perception.py` 9 个工具部分使用率低 | 增加 prompt 长度 | 监控使用率，按需精简 |
