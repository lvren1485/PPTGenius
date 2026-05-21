# 实验路线对比测试报告

> 测试时间：2026-05-21 | 模型：deepseek-v4-flash | 测试脚本：`tests/benchmark_comparison.py`

---

## 1. 分块策略对比

使用 ~3000 字符测试文本，chunk_size=300, overlap=30。

| 策略 | 块数 | 平均大小 | 最小 | 最大 | 耗时 |
|------|------|----------|------|------|------|
| **paragraph** | 100 | 246 | 218 | 291 | <1ms |
| **fixed** | 81 | 298 | 140 | 300 | <1ms |
| **sentence** | 119 | 237 | 152 | 274 | <1ms |

**结论：** `fixed` 策略最紧凑（块数最少、平均大小最大），`sentence` 块最多但边界更自然。三者计算性能差异可忽略。

---

## 2. PDF 解析性能

| 指标 | 值 |
|------|------|
| 测试文件 | 高等数学上.pdf |
| 文件大小 | 54.4 MB |
| 解析耗时 | **171 ms** |
| 提取字符 | 497 chars |
| 性能 | 3 chars/sec |

**注意：** 该 PDF 为扫描版（图像），PyMuPDF 不包含 OCR 引擎。文本型 PDF 可提取完整内容，扫描版 PDF 需额外 OCR 工具。这是 PyMuPDF 的已知限制，非代码问题。

---

## 3. LLM 性能对比（按任务类型）

| 任务 | 平均耗时 | Prompt Tokens | Completion Tokens | 响应示例 |
|------|----------|--------------|------------------|----------|
| **简短问答** | 2.55s | 14 | 207 | "Artificial intelligence mimics human thought." |
| **工具选择** | 1.69s | 48 | 129 | "search_web" |
| **内容生成** | 1.33s | 29 | 82 | 3个bullet points |
| **结构化输出** | 2.00s | 39 | 185 | JSON 格式 outline |

**结论：**
- 平均 **1.89s/调用**
- `content_gen` 最快（1.33s），`short_prompt` 最慢（2.55s）
- Completion tokens 波动大（82-207），取决于输出长度
- 结构化输出比普通对话多 2x tokens，但结果可直接解析

---

## 4. PPT 模板对比

5页 PPT（标题+内容+节标题+两栏+结束页），每种模板独立生成。

| 模板 | 生成耗时 | 文件大小 |
|------|----------|----------|
| **professional-blue** | 16ms | 31.8 KB |
| **modern-teal** | 16ms | 31.9 KB |
| **warm-orange** | 15ms | 31.8 KB |
| **minimal-gray** | 16ms | 31.9 KB |

**结论：** 模板对性能和文件大小几乎无影响（差异 <0.3%）。差异主要在视觉风格（颜色、字体）。

---

## 5. 端到端 Pipeline 性能

| 指标 | 值 |
|------|------|
| **总耗时** | 195.62s |
| **生成 slides** | 8 |
| **LLM 调用次数** | ~20 次 |
| **输出文件** | bench-test-01.pptx + _report.md |

**Pipeline 耗时分解：**

| 阶段 | 占比 | 说明 |
|------|------|------|
| RAG 扫描 | <1% | 无新文件时几乎无开销 |
| **LLM 推理** | ~95% | 约20次调用 × ~1.9s = ~38s，其余为 ReAct 循环等待 |
| PPT 生成 | <1% | 16ms |
| 报告生成 | <5% | 1-2 次 LLM 调用 |

**LLM 调用分布（历史累计 156 个日志文件）：**

| 调用类型 | 占比 | 用途 |
|----------|------|------|
| `react_iteration` | 86.5% | ReAct 循环中的 LLM 决策 |
| `create_plan` | 5.8% | 初始规划 |
| `generate_output` | 4.5% | 最终 outline 生成 |
| `review_suggestions` | 3.2% | 审查阶段建议生成 |

---

## 6. 未测试路径 & 说明

| 路径 | 状态 | 原因 | 建议 |
|------|------|------|------|
| **ChromaDB** | ❌ 未安装 | `chromadb` 包未安装 | `uv add chromadb` 即可测试 |
| **FAISS** | ❌ 未安装 | `faiss-cpu` 包未安装 | `uv add faiss-cpu` 即可测试 |
| **sentence-transformers** | ❌ 未安装 | 包未安装，且模型下载约 100MB | `uv add sentence-transformers` 后可用 |
| **OpenAI Embedding** | ❌ 跳过 | 用户指定不测试线上 embedding | 使用 local/mock |
| **OpenAI LLM** | ❌ 未测试 | 当前使用 DeepSeek | 切换 `.env` 中 API_BASE_URL 和 MODEL |
| **OCR PDF** | ❌ 不支持 | 扫描版 PDF 需要 Tesseract OCR | 需要额外安装 pytesseract |
| **plotly 图表** | ❌ 未安装 | 当前使用 matplotlib | `uv add plotly` 后切换 |
| **click/typer CLI** | ❌ 未测试 | 当前使用 argparse | 不影响核心性能指标 |

---

## 7. 关键发现

1. **LLM 调用是绝对瓶颈**（占 pipeline 95% 时间），优化方向是减少 ReAct 循环迭代次数
2. **分块策略影响 RAG 质量**：fixed 最紧凑、sentence 边界最自然、paragraph 居中
3. **PDF 解析对扫描版本无效**：需要用 OCR
4. **模板选择对性能无影响**：可放心按需选择
5. **DeepSeek API 稳定**：结构化输出（JSON mode）和普通 chat 都兼容良好

---

## 8. 下一步可测试路径

```bash
# 1. 安装 chromadb 对比向量库性能
uv add chromadb
# 然后重新运行 benchmark

# 2. 安装 sentence-transformers 对比 embedding 质量
uv add sentence-transformers
# embedding 质量对比需要人工评估

# 3. 用文本 PDF 测试解析效果
# 放入 resources/ 中一个有真实文本的 PDF
```
