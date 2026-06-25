# SearXNG 部署指南 · PPTGenius 网络搜索

## 环境

- Docker Desktop（已安装）
- SearXNG 镜像：`searxng/searxng:latest`

## 快速启动

```bash
# 1. 启动 SearXNG 容器（在 backend/ 目录下执行）
docker run -d --name searxng -p 8080:8080 \
  -e "SEARXNG_SECRET=pptgenius-local-dev-secret-key-2026" \
  -v "$(pwd)/searxng-data/settings.yml:/etc/searxng/settings.yml:ro" \
  searxng/searxng

# 2. 验证
curl "http://localhost:8080/search?q=test&format=json"

# 3. 配置后端（已有 config.local.yaml）
# web_search:
#   enabled: true
#   engine: "searxng"
#   max_results: 5
#   timeout: 15
#   searxng_base_url: "http://localhost:8080"

# 4. 管理
docker stop searxng       # 停止
docker start searxng      # 启动
docker rm searxng         # 删除（需先 stop）
```

## 配置说明

`searxng-data/settings.yml` — 主配置，已关闭限流和机器人检测以适应本地 API 调用。

限流和机器人检测通过 `settings.yml` 中的 `botdetection` 段关闭。

## 上游搜索引擎

SearXNG 默认启用多个引擎。可通过 `settings.yml` 的 `engines:` 段定制：
- Google、Startpage、Wikipedia 通常可用
- DuckDuckGo 可能触发 CAPTCHA
- Brave 可能限流

## 故障排查

| 问题 | 检查 |
|------|------|
| 403 Forbidden | `secret_key` 是否设置，`limiter: false` 是否生效 |
| 连接拒绝 | 容器是否运行：`docker ps --filter name=searxng` |
| 无结果 | `docker logs searxng` 查看引擎错误 |
| 搜索慢 | 增加 `outgoing.request_timeout` |
