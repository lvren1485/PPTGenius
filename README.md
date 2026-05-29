# PPTGenius

单人 AI PPT 生成网站。BM25 检索 + LangGraph Agent + FastAPI + MySQL。

预留有用户系统和多会话设计，待后期迭代。

## 环境准备

### MySQL

```bash
# 启动 MySQL (Windows)
mysqld --console

# 创建数据库
mysql -u {YOUR_USERNAME} -p -e "CREATE DATABASE IF NOT EXISTS pptgenius CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

<enter password when prompted>

# 创建测试库，如果需要运行测试
mysql -u {YOUR_USERNAME} -p -e "CREATE DATABASE IF NOT EXISTS pptgenius_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

<enter password when prompted>
```

### 配置

```bash
cd backend
cp config.yaml config.local.yaml
# 编辑 config.local.yaml，填入数据库连接和 API key
```

### 安装依赖

```bash
cd backend
uv sync
```

## 安装 Tabler 图标库 (PPT装饰素材)

PPTGenius 使用 [Tabler Icons](https://tabler.io/icons)（MIT 许可，5,800+ 图标）作为 PPT 矢量装饰素材。

```bash
# 1. 下载并解压
cd backend/src/pptgenius/resources/tabler
npm pack @tabler/icons
tar -xzf tabler-icons-*.tgz # 解压后会生成 package/ 目录，或者使用工具如 bandizip 直接解压 .tgz 文件

# 2. 拷贝元数据
cp package/icons.json icons_meta.json

# 3. 拷贝 outline SVG（用于 PPT 装饰）
mkdir -p svg
cp package/icons/outline/*.svg svg/

# 4. 清理
rm -rf package tabler-icons-*.tgz
```


## 运行

```bash
cd backend
uv run python main.py          # 启动 FastAPI (http://localhost:8000)
```

## 测试

```bash
cd backend
uv run pytest src/tests/ -v
```

## Benchmark

对已积累的 Outline / Presentation 数据进行离线评估，输出 HTML 报告到 `docs/benchmark_report.html`。

**前置条件：**

- 数据库中已有至少一条 Conversation，且至少有一个 Outline（通过正常使用产品生成）
- 如需测量 Traceability（大纲内容可追溯至知识库），需先上传知识文件

**评估维度：**

| 维度 | 说明 | 依赖 |
|---|---|---|
| Token 开销 | 按 Outline-only / PPT 会话分类统计 `message.estimated_cost` | `messages` 表 |
| Outline 分数 | 所有 Outline 的 `eval_score` 均值、标准差、最值 | `outlines` 表 |
| Traceability | 将 Outline 每句话作为查询搜索 BM25 知识库，统计可追溯句子占比 | `knowledge_files` 表 + BM25 索引 |

**运行：**

```bash
cd backend
uv run python src/benchmark.py
```

报告生成后浏览器打开 `docs/benchmark_report.html` 查看图表和逐会话明细。
