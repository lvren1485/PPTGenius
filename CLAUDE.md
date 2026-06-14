# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

# PPTGenius Project-Specific Conventions

> 版本: 0.2.0 | 基于 `docs/design/improvement.md`

---

## 硬性规则（`>` 强调项）

1. **禁止在 `src`、`pptgenius` 目录及其上级目录新建任何文件夹或文件，除非在 `improvement.md` 目录清单中明确列出。**
2. **所有文件必须经过静态测试，测试文件放在 `backend/src/tests` 目录下。**
3. **prompt 等静态资源必须放在 `resources` 目录下，代码中通过 `RESOURCES_DIR` 引用，禁止硬编码路径字符串。**
4. **原先的 agent 文件在 `agent_old/` 中，写新文件时必须查看对应的旧文件做参考。**
5. **`agent_id` 不存入任何表，仅作为内存中 `TokenCounter` 的 key。`token_cost_json` 仅存在于 `messages` 表。**
6. **单个 `.py` 文件尽量控制在 300 行以内，达到 500 行时拆分。单个函数 ≤ 60 行。不要因为行数限制牺牲可读性。**

## 子 Agent 工具的三段式调用

```python
# ① 调用前 push sentinel — 标记子 Agent 批次开始
push_sentinel(conversation_id)

# ② 运行子 Agent — 内部调用 build_llm() 生成 agent_id + TokenCountingMiddleware
result = await run_sub_agent(db, conversation_id, ...)

# ③ master.py 持久化时 pop_until_sentinel()
#    → 汇总所有 concurrent agent 的 token cost
#    → 写入 tool_result 消息的 token_cost_json
```

`master.py` 通过 `_SUB_AGENT_TOOLS` 集合（基于 `content_type`）识别子 Agent 工具：
```python
_SUB_AGENT_TOOLS: set[str] = {"gen_content", "mod_section", "evaluate", "explore"}
```

## 新增工具 Checklist

在 `_assemble_tools()` 中注册新工具时，需要同步完成：

1. 在 `_TOOL_CTYPE` 添加 `"tool_name" → "content_type"` 映射（≤32 字符）
2. 如果是子 Agent 工具，在 `_SUB_AGENT_TOOLS` 添加其 `content_type`
3. 在 `_assemble_tools()` 调用 `make_xxx(db, conversation_id)`
4. 子 Agent 工具必须在内部调用 `push_sentinel(conversation_id)`

## 资源路径约定

```python
from pptgenius.infrastructure.config.settings import RESOURCES_DIR

prompt_path = RESOURCES_DIR / "prompts" / "master.md"
system_prompt = prompt_path.read_text(encoding="utf-8")
```

prompt 模板文件统一放在 `backend/resources/prompts/` 下。
