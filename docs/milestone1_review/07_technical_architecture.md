# 技术架构与实现要点 — Milestone 1

## 系统架构

```
用户输入（主题 + 可选文档）
         │
         ▼
┌─────────────────────────────────────────┐
│  PPTGenerator (core.py)                  │  ← 顶层入口
│  ├── generate_outline()   L1: 大纲生成   │
│  └── enhance_with_rag()   L2: RAG 增强   │
└─────────────────────────────────────────┘
         │
    ┌────┼────────────────────┐
    ▼    ▼                    ▼
  LLM    RAG                Export
  模块   检索模块           导出模块
```

## 四层模块详解

### L1：LLM 模块 (llm/)
- **client.py**：OpenAI 兼容客户端，调用 DeepSeek API，temperature=0.6
- **prompts.py**：系统 Prompt 约束 JSON 输出格式，首次引入参考文本注入机制
- **enrich.py**：用 RAG 检索素材重写每页正文，temperature=0.45（事实性优先）

### L2：大纲模型 (outline/)
- **models.py**：Outline / SlideSpec dataclass，包含 title、bullets、body_paragraph、speaker_notes、rag_sources

### L3：RAG 检索 (rag/)
- **retriever.py**：BM25 检索器，中文正则分词，支持知识库 + 用户文档双源检索
- 知识库 corpus.json + 上传文档动态索引

### L4：PPT 导出 (export/)
- **pptx_export.py**：python-pptx 生成完整 .pptx，包含标题、要点、正文、备注

## 核心数据流

```
Topic + 参考文档文本
  → generate_outline() → Outline(JSON)
  → enhance_with_rag() → 检索 top_k 片段 → LLM 重写正文
  → export() → .pptx 文件
```

## 关键设计决策

| 决策点 | 方案 | 原因 |
|:-------|:-----|:-----|
| 大纲生成 + 内容增强分离 | 两阶段流水线 | 结构逻辑与内容事实解耦，便于独立优化 |
| 参考文本注入 | 8000字符上限 | 在上下文窗口内注入全文，减少编造 |
| 中文 BM25 | 正则分词 | 无外部 NLP 依赖，部署轻量 |
| 启发式降级 | 无 API Key 时规则填充 | 保证系统在任何条件下可运行 |
