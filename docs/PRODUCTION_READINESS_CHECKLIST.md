# 生产就绪检查清单

在将企业 RAG Agent 从本地或内部测试环境提升到正式使用前，请先完成这份检查清单。

## 密钥与环境变量

- 从 `.env.prod.example` 复制服务器本地 `.env.prod`，不要把真实 `.env.prod` 提交到 Git。
- 设置 `APP_ENV=production`。
- 为 `APP_USERNAME` 和 `APP_PASSWORD` 设置足够强的值。
- 确保 `POSTGRES_PASSWORD` 和 `DATABASE_URL` 中的数据库密码一致。
- 只在后端运行环境中设置 `DEEPSEEK_API_KEY`。
- 只在后端运行环境中设置 `EMBEDDING_API_KEY`。
- 不要把真实密钥放进 `frontend/.env`，因为 `VITE_` 变量会被打包进浏览器代码。
- 确保 `.env` 不进入 Git，也不要暴露在公开静态托管目录中。
- 运行 `python scripts/preflight_prod_check.py --env-file .env.prod`，确认没有错误。
- 使用 `docker login ccr.ccs.tencentyun.com` 登录腾讯云 TCR。
- 使用 `docker compose --env-file .env.prod -f compose.prod.yml pull` 拉取生产镜像。
- 使用 `docker compose --env-file .env.prod -f compose.prod.yml up -d` 启动生产栈，避免 Compose 解析阶段读不到 `${POSTGRES_PASSWORD}`。

## HTTPS、Cookie 与 CORS

- 前后端都通过 HTTPS 提供服务。
- 设置 `SESSION_COOKIE_SECURE=true`。
- 同站点部署时使用 `SESSION_COOKIE_SAMESITE=lax`。
- 只有在确实需要跨站点 cookie 且已启用 HTTPS 时，才使用 `SESSION_COOKIE_SAMESITE=none`。
- 设置 `CORS_ALLOW_LOCALHOST_REGEX=false`。
- 将 `CORS_ALLOWED_ORIGINS` 精确设置为生产前端来源。
- 对带凭证的浏览器会话，不要使用通配符 CORS 来源。
- 使用 Let's Encrypt 免费证书：运行 `bash init-ssl.sh your-domain.com` 自动完成申请和 nginx 配置切换。
- 证书续期由 crontab 自动执行（脚本已输出对应的 cron 配置），无需手动干预。

## 数据边界

- 在部署 schema 或数据访问逻辑变更前，先备份 PostgreSQL。
- 在重建或替换索引前，确认是否需要备份 Milvus 数据目录；如果允许清空向量索引，可清空 Milvus 后重新索引知识库。
- 将部署配置放在 `/opt/rag-agent`，将 PostgreSQL、Milvus、知识文件、证书和备份放在 `/data/rag-agent`。
- 将 `/data/rag-agent/knowledge`、`/data/rag-agent/postgres`、`/data/rag-agent/milvus`、`/data/rag-agent/backups`、`logs/` 和 `.env.prod` 放在公开 Web 根目录之外。
- 后端应作为服务进程运行在反向代理或服务管理器后面。

## 日志与审计

- 确认后端日志写入的是私有位置。
- 确认已启用日志轮转，或已监控存储上限。
- 确认可以通过 `/admin/audit` 查看管理员审计事件。
- 确认可以通过 `/admin/knowledge-audit` 查看知识访问审计事件。
- 在向更大范围运维人员开放日志访问前，先检查日志中是否包含敏感文档摘录。

## RAG 质量门禁

- 发布前运行维护好的 RAG 评测套件。
- 检查引用缺失、预期来源缺失和应拒答却未拒答等失败原因。
- 确认已上传知识文档在需要时带有部门元数据。
- 确认缺失的来源文件已被确认或清理。
- 确认失败的索引任务已修复，或已被明确标记为已确认。

## 运维检查

- 开放流量前确认 `/health` 返回 `ok`。
- 确认 `/admin/rag/status` 展示的文档数、分块数、BM25、向量存储和模型用量等信号符合预期。
- 确认普通账号和管理员账号下的登录、聊天、流式聊天、知识搜索、上传、同步和反馈流程都能正常工作。
- 确认每日 token 告警阈值符合部署预算。

## 回滚

- 保留上一版后端发布产物。
- 保留上一版前端 `dist/` 产物。
- 记录用于回滚的 PostgreSQL 备份时间戳。
- 记录用于回滚的 Milvus 数据目录备份时间戳；如果不保留向量索引，回滚后需要重新索引知识库。
- 如果回滚到旧代码，而 schema 或索引行为已发生变化，则恢复对应的 PostgreSQL 数据库快照。
