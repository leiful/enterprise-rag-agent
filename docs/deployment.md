# 部署说明

本文档说明如何以适合中小企业的方式部署本项目，覆盖本地开发、单机生产和基础安全要求。

## 部署模式

推荐按以下层次理解部署：

- 本地开发：应用运行在主机上，Docker 只运行 PostgreSQL。
- 单机生产：后端、PostgreSQL、nginx 运行在同一台服务器上。
- 后续扩展：保留向对象存储、企业文档系统和更完善运维体系扩展的空间。

## 本地开发部署

### 环境变量

在项目根目录创建 `.env`：

```powershell
Copy-Item .env.example .env
```

在前端目录创建 `frontend/.env`：

```powershell
Copy-Item frontend\.env.example frontend\.env
```

本地开发至少需要配置：

- `DEEPSEEK_API_KEY`
- `EMBEDDING_API_KEY`
- `POSTGRES_PASSWORD`
- `DATABASE_URL`
- `TEST_DATABASE_URL`
- `APP_USERNAME`
- `APP_PASSWORD`

说明：

- `.env` 只给后端和本地 `compose.yml` 使用。
- `frontend/.env` 只放浏览器可见配置，不要放密钥。
- 如果不自定义路径，可保持 `DEFAULT_KNOWLEDGE_SOURCE_PATH` 未设置，程序会使用默认目录。

### 启动 PostgreSQL

```powershell
docker compose up -d
```

本地 `compose.yml` 只启动 PostgreSQL，并从 `.env` 读取 `POSTGRES_PASSWORD`。

### 启动应用

后端：

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

前端：

```powershell
cd frontend
npm.cmd run dev
```

## 生产部署

### 生产前端配置

生产构建默认使用 `frontend/.env.production`：

```env
VITE_API_BASE=
```

留空表示优先走同源 API 请求，这适合通过 nginx 反向代理后端接口的单域名部署方式。

### 生产后端配置

生产环境建议在服务器项目目录创建 `.env.prod`。最小生产配置以 `.env.prod.example` 为准：

```env
DEEPSEEK_API_KEY=replace_with_real_deepseek_api_key
CHAT_MODEL=deepseek-v4-flash
CHAT_BASE_URL=https://api.deepseek.com
EMBEDDING_API_KEY=replace_with_real_embedding_api_key
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_MODEL=text-embedding-v4
APP_ENV=production
APP_USERNAME=admin
APP_PASSWORD=replace_with_a_strong_production_password
POSTGRES_PASSWORD=replace_with_production_db_password
DATABASE_URL=postgresql://ai_agent_user:replace_with_production_db_password@postgres:5432/ai_agent
DEFAULT_KNOWLEDGE_SOURCE_PATH=/app/knowledge_files
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_SAMESITE=lax
CORS_ALLOWED_ORIGINS=https://your-frontend-domain.example
CORS_ALLOW_LOCALHOST_REGEX=false
```

首次上线通常只需要替换 2 个 API key、管理员密码、数据库密码和生产域名。`POSTGRES_PASSWORD` 和 `DATABASE_URL` 中的数据库密码必须一致。

RAG、并发、rerank、分块和缓存等高级参数在 `backend/config.py` 中已有默认值。只有在生产压测或评测结果明确需要调优时，再把对应变量加入 `.env.prod`。

上线前可运行生产配置检查：

```powershell
.\.venv\Scripts\python.exe scripts\preflight_prod_check.py --env-file .env.prod
```

Linux 服务器可使用：

```bash
python scripts/preflight_prod_check.py --env-file .env.prod
```

### 生产启动流程

1. 登录腾讯云 TCR

```bash
docker login ccr.ccs.tencentyun.com
```

2. 检查生产配置

```bash
python scripts/preflight_prod_check.py --env-file .env.prod
```

3. 拉取生产镜像

```bash
docker compose --env-file .env.prod -f compose.prod.yml pull
```

4. 启动生产栈

```bash
docker compose --env-file .env.prod -f compose.prod.yml up -d
```

`--env-file .env.prod` 很重要：`compose.prod.yml` 中的 `${POSTGRES_PASSWORD}` 需要由 Docker Compose 在解析阶段读取。`backend` 服务的 `env_file` 只负责把变量传进后端容器，不能替代 Compose 解析阶段的变量插值。

`compose.prod.yml` 默认使用 GitHub Actions 推送到腾讯云 TCR 的后端和前端 nginx 镜像，因此服务器不需要安装 Node.js，也不需要在服务器上构建前端产物或应用镜像。

`compose.prod.yml` 当前包含：

- `postgres`
- `backend`
- `nginx`

### HTTPS 初始化与续期

生产环境建议先完成域名 DNS 解析，让域名指向服务器公网 IP，并确认 80 和 443 端口可访问。

首次申请 Let's Encrypt 证书：

```bash
bash init-ssl.sh your-domain.com
```

脚本会先用 HTTP-only nginx 暴露 ACME challenge 目录，申请证书后把 `nginx-ssl.conf` 中的 `YOUR_DOMAIN` 替换为真实域名并写入 `nginx.conf`，然后重启 nginx。完成后访问入口应为：

```text
https://your-domain.com
```

证书续期需要在服务器 crontab 中加入脚本输出的 renew 命令。续期后重启 nginx 才会加载新证书。

## 推荐部署边界

推荐的中小企业单机部署边界如下：

```text
Internet
  -> nginx
    -> frontend/dist
    -> backend API
      -> PostgreSQL
      -> pgvector 向量索引
      -> knowledge_files
```

建议遵循以下原则：

- 前端静态资源和 API 走同一域名，降低 Cookie 和 CORS 复杂度。
- 后端只运行在内网地址或容器网络中，由 nginx 反向代理访问。
- `knowledge_files/`、日志目录和 `.env` 不放到公开静态目录中。
- 优先使用 HTTPS。

## 生产安全基线

- 设置 `APP_ENV=production`
- 设置 `SESSION_COOKIE_SECURE=true`
- 设置 `CORS_ALLOW_LOCALHOST_REGEX=false`
- 把 `CORS_ALLOWED_ORIGINS` 限制到真实前端域名
- 使用强管理员密码和数据库密码
- 不要把后端密钥放进任何 `VITE_` 变量
- 不要把测试数据库连接到生产数据

## 常见问题

### 为什么修改了 `POSTGRES_PASSWORD` 但数据库密码没变

PostgreSQL 容器第一次初始化后，数据存放在 Docker 数据卷中。之后只改 `.env` 或 `compose.yml` 不会自动修改已有数据库用户密码，需要在数据库里手动执行 `ALTER USER`。

### 为什么生产环境建议同源部署

同源部署更适合中小企业的低复杂度场景，能减少跨域、Cookie 和代理配置错误，维护成本更低。

### 哪些目录不能公开暴露

至少不要把以下路径作为静态文件公开：

```text
.env
backend/
frontend/src/
knowledge_files/
logs/
```

## 进一步阅读

- 生产就绪检查：`docs/PRODUCTION_READINESS_CHECKLIST.md`
- 架构说明：`docs/architecture.md`
