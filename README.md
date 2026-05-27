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
