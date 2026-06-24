# 排障手册

## 1. 使用范围

遇到以下情况时，先按本手册取证，再提出修复方案：

- 生产页面空白、按钮失效、聊天失败或来源显示异常。
- API 返回 4xx、5xx、超时或前端请求失败。
- Docker 容器不健康、重启循环或镜像更新后行为异常。
- RAG 回答质量异常，例如答非所问、缺少来源、错误来源或应拒答却回答。
- 部署、证书、反向代理、数据库或知识库同步异常。

## 2. 排障原则

- 先取证，再修复；不要只凭报错文字猜根因。
- 先定位层级：浏览器、Nginx、后端、数据库、外部模型服务、知识库索引。
- 保留时间线：用户看到问题的时间、部署时间、日志时间和本地时区要对齐。
- 不把堆栈、Cookie、Token、密钥或敏感文档片段直接展示给普通用户。
- 修复后必须补回归测试，或说明为什么无法补。
- 修复后按 `docs/testing.md` 做轻量复盘，检查是否需要补文档、脚本、测试或配置。

## 3. 快速分层检查

### 浏览器

- 打开生产页。
- 检查页面是否空白、是否能登录、是否能打开历史会话。
- 检查 Console 是否有红色运行时错误。
- 检查 Network 中失败请求的路径、状态码和响应摘要。

常见判断：

- Console 有 `TypeError`：优先查前端组件、props、状态或历史数据兼容。
- 请求 401/403：优先查登录状态、Cookie、权限和 CORS。
- 请求 502/504：优先查 Nginx 到后端连接、后端健康和超时。

### Nginx

```bash
docker logs ai-agent-nginx --tail 100
docker inspect ai-agent-nginx --format '{{json .State.Health}}'
```

常见判断：

- `499`：常见于客户端主动断开。
- `502`：常见于代理不到后端或后端拒绝连接。
- `504`：常见于后端响应超时。

### 后端

```bash
docker logs ai-agent-backend --tail 100
docker inspect ai-agent-backend --format '{{json .State.Health}}'
```

重点关注：

- 启动错误。
- 数据库连接错误。
- 模型 API 错误。
- 知识库检索或索引异常。
- 认证、权限或 CORS 警告。

### 容器状态

```bash
docker compose --env-file .env.prod -f compose.prod.yml ps
```

检查：

- `postgres` 是否健康。
- `backend` 是否健康。
- `nginx` 是否健康。
- 镜像是否已更新到预期版本。

## 4. 常用时间窗口命令

用户给出本地时间时，先确认服务器日志是否使用 UTC。

```bash
docker logs ai-agent-backend --since "YYYY-MM-DDTHH:MM:SS" --until "YYYY-MM-DDTHH:MM:SS"
docker logs ai-agent-nginx --since "YYYY-MM-DDTHH:MM:SS" --until "YYYY-MM-DDTHH:MM:SS"
```

如果不确定时间窗口，先看最近日志：

```bash
docker logs ai-agent-backend --tail 300
docker logs ai-agent-nginx --tail 300
```

## 5. RAG 质量问题排查

回答质量问题要区分：

- 模型没有正确使用证据。
- 知识库没有召回足够证据。
- 知识源过期、缺失或权限过滤导致证据不可见。
- 前端展示和后端来源记录不一致。

检查顺序：

1. 用户问题原文。
2. 回答正文和引用标签。
3. 返回 sources 的 `document_id`、`chunk_index`、`score`、部门权限和文档版本。
4. `/admin/rag/status` 中知识库状态。
5. 相关 RAG 评测用例是否覆盖该问题。

## 6. 复盘模板

生产问题修复后，用以下模板记录到对话、Issue、PR 或文档中：

```text
现象：
影响范围：
时间线：
证据：
根因：
修复：
验证：
为什么没有提前发现：
缺失的防线：
建议沉淀：
是否需要用户确认：
```

## 7. 何时升级为脚本或 Skill

同一类排障步骤重复 3 次以上时，优先考虑：

- 写成 `scripts/` 预检或日志收集脚本。
- 写入更具体的 `docs/` 操作手册。
- 抽成 Codex Skill。
- 加入 CI 或发布门禁。
