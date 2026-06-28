# PPTGenius Benchmark 设计方案

> 版本: 0.2.0 | 日期: 2026-06-19

---

## 一、架构变更

### 1.1 删除项

| 删除 | 原因 |
|------|------|
| `docs/report/` 整个目录 | 命名不当，旧 benchmark 逻辑已完全失效 |
| `backend/benchmark.py` (735 行) | 依赖已弃用的 Evaluator + BM25 溯源，重写 |

### 1.2 新目录结构

```
backend/src/tests/benchmark/
├── __init__.py
├── run.py                    # CLI 入口: uv run python -m tests.benchmark.run
├── cost_and_time.py          # B1: 生成时间与成本 (messages 表)
├── outline_quality.py        # B2: 大纲质量 LLM 评分 (DeepSeek V4 Pro)
├── visual_quality.py         # B3: PPT 视觉质量 (agent_outputs JSON 自动检查)
├── report.py                 # 汇总报告生成 (markdown)
└── prompts/
    └── outline_judge.md      # 大纲评分 prompt (量化评分卡)
```

每个 benchmark 模块独立，可单独运行。`run.py` 串联全部模块并输出汇总报告。

---

## 二、B1: 生成时间与成本

**数据来源**: `messages` 表（不生成新数据，只读已有记录）

### 2.1 对话分块逻辑

将一个 conversation 的所有 messages 按 `idx` 排序，按 `user` 消息切分为多个**对话块 (turn)**：

```
Turn 1: [user] → [tool_call] → [tool_result] → ... → [assistant]
Turn 2: [user] → [tool_call] → [tool_result] → ... → [assistant]
...
```

每个 turn 从一条 `role=user, content_type=text` 开始，到下一条 user 消息之前结束。

### 2.2 大纲生成识别

一个 turn 被识别为**大纲生成**当且仅当该 turn 的 tool_call/tool_result 消息中连续包含以下 `content_type`：

```
explore → gen_content   (先探索后生成)
```

识别规则：
1. 扫描 turn 内所有 `role=tool_call` 的消息
2. 如果存在 `content_type=explore` 且之后存在 `content_type=gen_content` → 大纲生成 turn
3. 仅取**首次出现**的大纲生成 turn（后续修改不计入）

### 2.3 PPT 生成识别

一个 turn 被识别为 **PPT 生成**当且仅当 tool_call 中包含：

```
ppt_style → slides_content   (先选样式后生成内容)
```

同样仅取首次出现。

### 2.4 时间计算

```python
# 大纲 / PPT 生成时间
start = turn 内第一条 user 消息的 created_at
end   = turn 内最后一条 tool_result 消息的 created_at  # assistant 的时间戳有已知 bug，不用
duration = end - start
```

**Evaluator 时间剔除**：如果 turn 内存在 `content_type=evaluate` 的 tool_call/tool_result 对，将该对的时间段从 duration 中减去：

```python
for each evaluate_tool_call:
    eval_start = evaluate_tool_call.created_at
    eval_end   = 对应 evaluate_tool_result.created_at
    duration -= (eval_end - eval_start)
```

### 2.5 成本计算

```python
# 总成本 = turn 内所有消息的 estimated_cost 之和
total_cost = sum(m.estimated_cost for m in turn_messages if m.estimated_cost)

# 剔除 Evaluator 成本
for each evaluate pair (tool_call + tool_result):
    total_cost -= evaluate_tool_result.estimated_cost or 0
```

### 2.6 输出指标

| 指标 | 计算 | 粒度 |
|------|------|------|
| 大纲生成时间 | 见 2.4 | per-conversation |
| 大纲生成成本 | 见 2.5 | per-conversation |
| 大纲每页成本 | total_cost / outline.slide_count | per-slide |
| PPT 生成时间 | 同上 | per-conversation |
| PPT 生成成本 | 同上 | per-conversation |
| PPT 每页成本 | total_cost / presentation.slide_count | per-slide |
| Evaluator 剔除时间 | 被减去的时间总和 | 参考值 |
| Evaluator 剔除成本 | 被减去的成本总和 | 参考值 |

### 2.7 Retry 次数

从 messages 表中统计同一 turn 内相同 `content_type` 的 tool_call 出现次数。如果 `gen_content` 出现 2 次以上，说明发生了 retry。

```python
retry_count = count(content_type == "gen_content" in turn) - 1  # 首次不算 retry
```

---

## 三、B2: 大纲质量 (LLM-as-Judge)

### 3.1 评估模型

使用 **DeepSeek V4 Pro**（而非生成时使用的 V4 Flash）。评估模型应高于生成模型，避免自我评价偏差。

### 3.2 量化评分卡

不使用开放式打分，而是定义严格的量化评分卡。Judge 对每个维度按具体标准给出 1-10 分，附带扣分理由。

**评分维度 (4 个)**：

#### D1: 结构合理性 (1-10)

| 分段 | 标准 |
|------|------|
| 9-10 | section 划分清晰且均衡，每 section 3-6 页，覆盖主题全部核心方面 |
| 7-8 | section 划分合理但略有不均（某 section 页数过多/过少），覆盖面充分 |
| 5-6 | section 划分存在问题（过粗/过细/遗漏重要方面），但整体可用 |
| 3-4 | section 划分混乱，多个方面遗漏或重复 |
| 1-2 | 无有效 section 结构 |

#### D2: 页间逻辑连贯性 (1-10)

| 分段 | 标准 |
|------|------|
| 9-10 | 页面顺序形成清晰的叙事递进（总→分、因→果、问题→方案），过渡自然 |
| 7-8 | 整体有逻辑线索但 1-2 处过渡生硬 |
| 5-6 | 部分页面可独立成章但缺乏明确的叙事线索 |
| 3-4 | 页面顺序基本随意，逻辑关系不明确 |
| 1-2 | 完全无逻辑组织 |

#### D3: 内容充实度 (1-10)

| 分段 | 标准 |
|------|------|
| 9-10 | 每页有 3+ 个具体要点，含数据/案例/引用，详细内容充实，不泛泛而谈 |
| 7-8 | 多数页有具体内容，少数页偏概括性 |
| 5-6 | 约半数页内容充实，半数页仅有概括性描述 |
| 3-4 | 多数页仅有一两句话或空泛描述 |
| 1-2 | 几乎无实质内容 |

#### D4: 视觉建议合理性 (1-10)

| 分段 | 标准 |
|------|------|
| 9-10 | 每页都有合理的 recommended_ppt_format 和 visual_note，图表/图片建议贴合内容 |
| 7-8 | 多数页有视觉建议且合理，少数缺失 |
| 5-6 | 视觉建议存在但部分不合理（如纯数据页建议纯文本） |
| 3-4 | 视觉建议大量缺失或明显不合理 |
| 1-2 | 无视觉建议 |

### 3.3 Judge Prompt 结构

```markdown
你是一个 PPT 大纲质量评审专家。请严格按照以下评分卡对大纲进行评分。

## 评分规则
- 每个维度独立打分 (1-10)，必须严格按照评分标准给分
- 每个维度必须给出 1-2 条扣分理由（满分也需说明优点）
- 不允许给出 0 分或 >10 的分数
- 倾向于严格打分：没有明确证据支持高分时，给中间分

## 大纲内容
{outline_json}

## 主题
{topic}

## 请输出 JSON:
{
  "structure": {"score": N, "reason": "..."},
  "coherence": {"score": N, "reason": "..."},
  "richness":  {"score": N, "reason": "..."},
  "visual":    {"score": N, "reason": "..."}
}
```

### 3.4 采样与聚合

- 每个大纲调用 Judge **3 次**，取各维度的**中位数**（非均值，抗异常值）
- 最终分 = 4 个维度分数的算术均值
- 记录每次评分的 token 消耗和成本

---

## 四、B3: PPT 视觉质量 (自动化)

**数据来源**: `presentation_slides.agent_outputs` JSON + `styles` 表

所有检查直接分析 JSON，不需要渲染 .pptx 或调用 LLM。

### 4.1 检查项

| 编号 | 指标 | 计算逻辑 | 阈值 |
|------|------|---------|------|
| V1 | 元素越界率 | position 超出 13.33×7.5" 的元素数 / 总元素数 | 0% |
| V2 | 非 shape 重叠率 | IoU > 30% 且双方非 shape 的元素对 / 总元素对 | < 5% |
| V3 | 文字溢出率 | textbox 估算容量 < 实际字数的元素 / textbox 总数 | < 10% |
| V4 | 样式一致性 | 元素 fill.color 在 style.colors_json 中的比例 | ≥ 90% |
| V5 | 最小字号合规率 | font_size ≥ 11pt 的 textbox / textbox 总数 | 100% |
| V6 | z-order 合理性 | z_order 遵循参照表的元素 / 总元素 | ≥ 95% |
| V7 | Part 完成率 | plan.parts 中 status=complete 的 / 总 part 数 | 100% |
| V8 | 背景设置率 | 有 background 的 slide / 总 slide 数 | ≥ 95% |
| V9 | 装饰一致性 | 同一 slide 同时出现 emoji + icon 的次数 | 0 |

### 4.2 实现

复用 `spatial_check.py` 和 `decor_check.py` 的检测逻辑，提取为纯函数（输入 agent_outputs dict，输出指标值）。

---

## 五、报告格式

### 5.1 输出路径

```
docs/benchmark/
├── benchmark_report.md       # 汇总报告
├── cost_time_detail.md       # B1 详细数据
├── outline_scores.md         # B2 各大纲评分明细
└── visual_quality.md         # B3 各 slide 检查明细
```

### 5.2 汇总报告结构

```markdown
# PPTGenius Benchmark Report
Generated: {timestamp} | {N} conversations

## 生成时间与成本 (B1)
| 类型 | 对话数 | 平均时间 | 平均成本 | 每页成本 |
|------|--------|---------|---------|---------|
| 大纲 | N | Xm Ys | ¥X.XX | ¥X.XX |
| PPT  | N | Xm Ys | ¥X.XX | ¥X.XX |

## 大纲质量 (B2)
| 大纲 | 结构 | 连贯 | 充实 | 视觉建议 | 均分 |
|------|------|------|------|---------|------|

## PPT 视觉质量 (B3)
| 指标 | 目标 | 实际 | 达标 |
|------|------|------|------|

## Per-Conversation Detail
| Conv | 类型 | 时间 | 成本 | 大纲分 | 视觉达标率 |
|------|------|------|------|--------|-----------|
```

---

## 六、实现计划

| 阶段 | 模块 | 工作量 | 优先级 |
|------|------|--------|--------|
| P0 | `cost_and_time.py` | ~120 行 | 最高——纯 DB 读取，无外部依赖 |
| P0 | `visual_quality.py` | ~100 行 | 最高——复用已有检查逻辑 |
| P1 | `outline_quality.py` | ~80 行 + prompt | 高——需要 V4 Pro API 调用 |
| P1 | `report.py` + `run.py` | ~80 行 | 高——汇总输出 |

总计约 **380 行**新代码，替代旧 `benchmark.py` 的 735 行。
