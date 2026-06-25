# 安全手册

## 1. 使用范围

涉及以下内容时，必须阅读本手册：

- 环境变量、密钥、Token、Cookie、数据库密码和第三方凭证。
- 登录、会话、权限、部门隔离和管理员操作。
- CORS、HTTPS、Nginx、公开目录和静态资源暴露。
- 日志、反馈、审计、错误报告和用户可见提示。
- 生产部署、备份、恢复和运维账号。

## 2. 密钥与配置

- 真实密钥只能通过服务器环境变量、`.env.prod`、GitHub Secrets 或云服务安全配置注入。
- 不要提交 `.env`、`.env.prod`、Cookie、Token、私钥、数据库密码或个人机器配置。
- `.env.example` 和 `.env.prod.example` 只放变量名、示例值和说明，不放真实值。
- 不要把任何后端密钥放入 `VITE_` 前端变量。
- GitHub Actions Secrets 只用于 CI/CD，不在日志中打印明文。

## 3. 认证与权限

- 权限检查必须放在后端；前端显示控制不能替代后端授权。
- 管理接口必须要求管理员权限。
- 知识库访问应考虑部门权限、文档版本和来源状态。
- 登录失败、锁定和会话过期提示应面向用户友好，不暴露内部实现。

## 4. Cookie、HTTPS 与 CORS

生产环境建议：

```env
APP_ENV=production
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_SAMESITE=lax
CORS_ALLOW_LOCALHOST_REGEX=false
CORS_ALLOWED_ORIGINS=https://your-domain.example
```

- 生产环境优先同源部署，减少跨域和 Cookie 配置复杂度。
- 带凭证的浏览器请求不要使用通配符 CORS 来源。
- `SESSION_COOKIE_SAMESITE=none` 只在确实需要跨站点 Cookie 且已启用 HTTPS 时使用。
- 生产环境必须优先使用 HTTPS。

## 5. 日志与错误提示

不得在日志、反馈、审计或用户提示中暴露：

- 密码、API key、Token、Cookie、私钥。
- 完整连接串。
- 不必要的个人敏感信息。
- 大段敏感文档原文。
- 面向普通用户的堆栈和内部异常。

建议做法：

- 用户提示给出可理解的恢复建议。
- 详细错误进入后端日志，但要脱敏。
- 排障时只引用必要片段，不复制完整敏感内容。

## 6. 生产目录边界

不要公开暴露：

```text
.env
.env.prod
backend/
frontend/src/
knowledge_files/
/data/rag-agent/knowledge
/data/rag-agent/postgres
/data/rag-agent/milvus
/data/rag-agent/backups
logs/
```

推荐边界：

- `/opt/rag-agent` 放部署配置。
- `/data/rag-agent` 放 PostgreSQL、Milvus、知识文件、证书和备份。
- Nginx 只暴露前端静态资源、API 代理和 ACME challenge。

## 7. 备份与恢复

- 数据库结构、权限、chunk 文本、元数据和 BM25 数据在 PostgreSQL 中；向量索引在 Milvus 中，重要变更前先确认是否需要备份或是否可以重建。
- 备份文件放在非公开目录。
- 回滚代码前，确认 schema 和索引行为是否兼容。
- 恢复前先确认目标环境，避免把测试数据覆盖到生产。

## 8. 安全复盘

如果发现安全风险或配置缺口，复盘时回答：

1. 风险是否已经影响生产。
2. 是否有密钥或敏感数据暴露。
3. 是否需要轮换密钥、密码或 Cookie secret。
4. 是否需要补文档、脚本、测试、CI 或部署检查。
5. 是否需要通知用户或限制访问。
