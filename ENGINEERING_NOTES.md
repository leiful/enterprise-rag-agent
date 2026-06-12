# 工程笔记

这份文档用于记录本地企业 RAG 项目的维护信息。面向使用者的安装、启动和常用命令放在 `README.md`；架构边界、维护规则和运维注意事项放在这里。

## 当前架构

```text
backend/        FastAPI API、认证、路由、服务、RAG chains、数据库辅助函数、测试
frontend/       Vue 3 运维控制台
knowledge_files/ 本地知识文档，Git 忽略
chroma_db/      本地 Chroma 持久化目录，Git 忽略
rag_eval/       评估问题和报告
scripts/        RAG 评估和索引维护脚本
compose.yml     本地开发用 PostgreSQL 服务
```

后端使用 PostgreSQL 保存应用元数据，使用 Chroma 做向量持久化。PostgreSQL 保存用户、会话、对话、消息、知识文档元数据、向量 chunk 元数据、BM25 索引、知识源、索引任务、RAG 反馈、模型用量、管理员审计事件和知识访问审计事件。

## 本地服务边界

推荐的本地开发结构是：

```text
Windows 主机：
  源码
  Python 虚拟环境
  前端 Node 依赖
  后端和前端开发服务
  .env
  knowledge_files/
  chroma_db/

Docker：
  只运行 PostgreSQL
```

普通本地开发不要把整个应用搬进 Docker，除非有明确原因。应用跑在 Windows 上更方便调试，Docker 只隔离 PostgreSQL。

## PostgreSQL 维护

`compose.yml` 使用 `postgres:16` 启动名为 `ai-agent-postgres` 的容器，并把数据持久化到 Docker 管理的 volume。删除容器不会删除数据库数据；删除 volume 才会删除数据库数据。

安全命令：

```powershell
docker compose up -d
docker compose stop
docker compose down
```

会删除本地数据库数据的危险命令：

```powershell
docker compose down -v
```

`POSTGRES_USER`、`POSTGRES_PASSWORD` 和 `POSTGRES_DB` 只在新的 PostgreSQL 数据 volume 首次初始化时生效。如果 volume 已经存在，修改 `compose.yml` 里的这些值不会修改已有数据库用户或密码。

测试数据库和应用数据库必须分开：

```text
DATABASE_URL      -> ai_agent
TEST_DATABASE_URL -> ai_agent_test
```

不要把 `TEST_DATABASE_URL` 指向 `ai_agent` 或生产数据。集成测试会清空测试数据库里的应用表。

## 运行配置

后端从项目根目录的 `.env` 加载配置。重要配置：

```env
DEEPSEEK_API_KEY=your_model_provider_key
APP_ENV=development
EMBEDDING_API_KEY=your_embedding_provider_key
DATABASE_URL=postgresql://ai_agent_user:password@localhost:5432/ai_agent
TEST_DATABASE_URL=postgresql://ai_agent_test_user:password@localhost:5432/ai_agent_test
DATABASE_CONNECT_TIMEOUT_SECONDS=3
VECTOR_STORE_BACKEND=chroma
CHROMA_PERSIST_DIR=E:\Project\AI Agent\chroma_db
CHROMA_COLLECTION_NAME=agent_knowledge
DEFAULT_KNOWLEDGE_SOURCE_PATH=E:\Project\AI Agent\knowledge_files
APP_USERNAME=admin
APP_PASSWORD=change_this_local_password
SESSION_MAX_AGE_SECONDS=604800
SESSION_COOKIE_SECURE=false
SESSION_COOKIE_SAMESITE=lax
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
CORS_ALLOW_LOCALHOST_REGEX=true
```

前端配置位于 `frontend/.env`：

```env
VITE_API_BASE=http://localhost:8000
```

不要把真实 API key 或密码放进前端 `VITE_` 变量。前端环境变量会被打包进浏览器可见的代码。

## 测试规则

使用维护好的测试分组：

```powershell
.\.venv\Scripts\python.exe run_tests.py --group fast
.\.venv\Scripts\python.exe run_tests.py --group database
.\.venv\Scripts\python.exe run_tests.py --group vector
.\.venv\Scripts\python.exe run_tests.py --group api
```

`database`、`vector` 和 `api` 必须串行运行。它们共用并重置 `ai_agent_test`；并行运行可能造成死锁、默认用户重复和外键错误。

`database.connect()` 使用 `DATABASE_CONNECT_TIMEOUT_SECONDS`，所以 PostgreSQL 不可用时会快速失败。测试工具会先探测一次 `TEST_DATABASE_URL`，测试库不可用时跳过集成测试。

## RAG 流程

企业 RAG 路径包括：

- 文件上传或本地知识源同步。
- 解析 text、Markdown、PDF、DOCX、CSV 和 Excel。
- 基于标题感知的 chunk 切分，可选语义切分。
- 通过 OpenAI-compatible embedding API 生成 embedding。
- Chroma 向量持久化。
- PostgreSQL chunk 元数据和 BM25 索引存储。
- 向量检索加 BM25 的混合检索。
- 可选 query rewrite、multi-query expansion 和 rerank。
- 基于部门的访问过滤。
- 基于生效日期和过期日期的生命周期过滤。
- RAG 访问审计和用户反馈收集。

运维端点：

```text
GET /admin/rag/status
GET /admin/rag/eval
GET /admin/audit
GET /admin/knowledge-audit
```

## 知识源

注册的知识源保存在 PostgreSQL。启动时如果没有任何知识源，会创建默认本地知识源。同步知识源时，会为变更文件排队索引任务，跳过未变化文件，并移除已从源目录消失文件的索引。

默认本地知识源路径由 `DEFAULT_KNOWLEDGE_SOURCE_PATH` 控制；未配置时回退到项目的 `knowledge_files/` 目录。

当前只支持本地目录知识源。未来的企业连接器可以从这一层扩展到对象存储、Confluence、SharePoint、飞书或其他文档系统。

## 认证与安全

浏览器应用通过 `/login` 登录。后端把 session 存在 PostgreSQL，并向浏览器发送 `HttpOnly` session cookie。受保护路由要求携带该 cookie。

生产部署要求：

- 使用 HTTPS。
- 设置 `APP_ENV=production`。
- 设置 `SESSION_COOKIE_SECURE=true`。
- 设置 `CORS_ALLOW_LOCALHOST_REGEX=false`。
- 把 `CORS_ALLOWED_ORIGINS` 限制为真实前端域名。
- 使用强管理员凭据和数据库密码。
- 不要把 `.env`、Chroma 数据、PostgreSQL 数据、日志和上传的知识文件暴露为公开静态文件。
- 模型 API key 和 embedding API key 只属于后端密钥。

## 部署边界

只把前端构建产物作为静态文件部署：

```text
frontend/dist/
```

不要把这些路径作为公开静态内容暴露：

```text
.env
backend/
frontend/src/
frontend/node_modules/
knowledge_files/
chroma_db/
logs/
```

后端应该作为服务进程运行在反向代理或平台服务管理器后面。生产环境后续可以把后端容器化，并用 Nginx 托管 `frontend/dist/`、反向代理 API 请求。

## 变更检查清单

编辑前先确认影响层：

```text
backend
frontend
configuration
tests
documentation
deployment
```

编辑后：

- 运行最窄范围的相关测试。
- 涉及认证、数据库、索引或 RAG 时，运行完整后端测试分组。
- UI 代码变更后构建前端。
- 启动方式、配置、schema 或部署行为变化时更新 README 或本文件。
- 提交前检查 `git diff`。
