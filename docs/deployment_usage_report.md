# PPTGenius 部署与使用报告

## 1. 部署结果

PPTGenius 已部署到华为云 ECS，并通过公网 IP 提供 Web 访问。

- 访问地址：http://113.44.39.109/
- 前端服务：Nginx 静态站点
- 后端服务：FastAPI + Uvicorn，监听 127.0.0.1:8000
- 数据库：MySQL 8.0，本机部署
- 部署目录：/opt/pptgenius
- 工作区目录：/var/lib/pptgenius/workspace
- 日志目录：/var/log/pptgenius

## 2. 服务器环境

- 云厂商：Huawei Cloud Service
- 操作系统：Huawei Cloud EulerOS 2.0 x86_64
- CPU：2 vCPU
- 内存：约 4 GB
- 系统盘：40 GB，部署后约使用 3.4 GB
- 开放端口：80 Web，22 SSH

## 3. 已安装组件

- Nginx 1.21.5
- MySQL 8.0.46
- uv 0.11.25
- Python 3.12.13
- PPTGenius 后端运行依赖
- PPTGenius 前端构建产物

## 4. 服务状态

以下服务已设置为开机自启：

- mysqld
- nginx
- pptgenius

常用检查命令：

```bash
systemctl status pptgenius
systemctl status nginx
systemctl status mysqld
ss -ltnp | grep -E ":80|:8000|:3306"
```

## 5. 部署结构

```text
/opt/pptgenius/
├── backend/                 # 后端源码、配置和 Python 虚拟环境
│   ├── config.local.yaml     # 生产配置
│   ├── .venv/                # Python 3.12 虚拟环境
│   └── src/pptgenius/        # FastAPI 与业务代码
├── frontend/dist/            # 前端静态构建产物
├── docs/                     # 项目文档
└── DEPLOYMENT_REPORT.md      # 本报告
```

## 6. Nginx 配置

配置文件：/etc/nginx/conf.d/pptgenius.conf

- / 访问前端 Vue 单页应用
- /api/ 反向代理到 http://127.0.0.1:8000/api/
- 已关闭代理缓冲，支持 SSE 流式接口
- 上传大小限制：100 MB
- API 超时：600 秒

验证命令：

```bash
nginx -t
curl -i http://127.0.0.1/
curl -i http://127.0.0.1/api/system/health
```

说明：/api/system/health 当前会返回 401 缺少认证令牌，这是后端认证中间件的预期行为，表示 Nginx 到后端链路已打通。

## 7. 数据库配置

- 数据库名：pptgenius
- 应用用户：pptgenius
- 数据库密码保存位置：/root/.pptgenius_db_pass
- 配置文件位置：/opt/pptgenius/backend/config.local.yaml

已初始化的数据表包括：

- users
- conversations
- messages
- knowledge_files
- knowledge_chunks
- outlines
- outline_sections
- outline_slides
- outline_snapshots
- presentations
- presentation_slides
- presentation_snapshots
- styles

## 8. 重要待配置项

当前部署可以打开网站、注册登录和访问 API，但真正调用 AI 生成 PPT 前，需要配置 DeepSeek API Key。

编辑文件：

```bash
vi /opt/pptgenius/backend/config.local.yaml
```

将以下占位符替换为真实 Key：

```yaml
llm:
  api_key: "REPLACE_WITH_DEEPSEEK_API_KEY"
```

修改后重启后端：

```bash
systemctl restart pptgenius
```

## 9. 使用方法

1. 浏览器访问 http://113.44.39.109/
2. 点击注册，创建账号。
3. 登录系统。
4. 在聊天页面输入 PPT 主题，例如“生成一份关于新能源汽车市场趋势的 10 页 PPT”。
5. 可上传 PDF、DOCX、XLSX 等资料作为知识库来源。
6. 系统会通过 SSE 流式返回 Agent 执行进度。
7. 生成完成后可在 PPT 页面预览和下载 .pptx 文件。

注意：如果没有配置 DeepSeek API Key，涉及 LLM 的生成操作会失败。

## 10. 运维命令

查看后端日志：

```bash
journalctl -u pptgenius -f
```

查看应用日志：

```bash
tail -f /var/log/pptgenius/app.log
```

重启服务：

```bash
systemctl restart pptgenius
systemctl restart nginx
systemctl restart mysqld
```

更新部署：

```bash
# 上传新代码到 /opt/pptgenius 后
systemctl restart pptgenius
nginx -t && systemctl reload nginx
```

备份数据库：

```bash
mysqldump -uroot pptgenius > /root/pptgenius_$(date +%F).sql
```

备份用户文件：

```bash
tar -czf /root/pptgenius_workspace_$(date +%F).tar.gz /var/lib/pptgenius/workspace
```

## 11. 当前限制与建议

- 当前服务器为 2C/4G，适合演示、课程验收、小规模试用。
- PPT 生成和文档解析会消耗较多内存，不建议高并发使用。
- 如用于正式生产，建议升级到 4C/8G 或 4C/16G，并将 MySQL 迁移到云 RDS。
- 当前使用 HTTP，正式上线建议绑定域名并配置 HTTPS。
- 当前 workspace 使用本地磁盘，生产环境建议迁移到对象存储或云 NAS。
- DeepSeek API Key 应只保存在服务器配置或密钥管理系统中，不要提交到代码仓库。

## 12. 验收记录

- SSH 密钥登录：通过
- Nginx 配置检查：通过
- 前端公网访问：http://113.44.39.109/ 返回 200
- 后端服务：pptgenius active running
- API 反向代理：http://113.44.39.109/api/system/health 返回 401，符合认证拦截预期
- MySQL：已启动并初始化表结构
- 开机自启：mysqld、nginx、pptgenius 均已 enabled
