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

### SearXNG（可选 — 网络搜索替代引擎）

DuckDuckGo 在中国大陆可能不稳定。建议部署本地 SearXNG 实例替代。

```bash
# 1. 拉取并启动 SearXNG（需 Docker Desktop）
docker run -d --name searxng -p 8080:8080 \
  -e "SEARXNG_SECRET=pptgenius-local-dev-secret-key-2026" \
  -v "$(pwd)/searxng-data/settings.yml:/etc/searxng/settings.yml:ro" \
  searxng/searxng

# 2. 验证
curl "http://localhost:8080/search?q=test&format=json"
```

然后在 `config.local.yaml` 中切换引擎：
```yaml
web_search:
  engine: "searxng"
  searxng_base_url: "http://localhost:8080"
```

详细配置见 `backend/searxng-data/README.md`。

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

对已积累的 Outline / Presentation 数据进行离线评估，输出报告到 `docs/benchmark/`。

**三个评估模块：**

| 模块 | 说明 | 数据来源 |
|------|------|---------|
| B1 生成时间与成本 | 大纲/PPT 生成耗时、per-slide 成本、retry 次数 | `messages` 表 |
| B2 大纲质量 | LLM Judge 量化评分 (结构/连贯/充实/视觉，1-10) | DeepSeek V4 Pro |
| B3 PPT 视觉质量 | 越界、重叠、溢出、样式一致性等 9 项自动检查 | `agent_outputs` JSON |

**运行：**

```bash
cd backend

# 完整评估（含 LLM Judge，会产生 API 费用）
uv run python -m tests.benchmark.run

# 跳过 LLM Judge（仅统计成本/时间 + 视觉检查，无 API 费用）
uv run python -m tests.benchmark.run --skip-judge

# 指定 Judge 模型
uv run python -m tests.benchmark.run --judge-model deepseek-chat
```

报告输出到 `docs/benchmark/benchmark_report.md`。

## 前端

Vue 3 + Element Plus + TypeScript，Vite 构建，开发时通过代理转发 API。

```bash
cd frontend
npm install
npm run dev                    # 启动开发服务器 (http://localhost:5173)
```

访问 `http://localhost:5173`，API 请求自动代理至 `http://localhost:8000`。

**前置条件：** 后端已启动（`cd backend && uv run python main.py`）。

### 构建

```bash
cd frontend
npm run build                  # 输出到 frontend/dist/
```
