# 测试指南

## 1. 使用范围

修改以下内容时，必须阅读并执行本指南：

- Vue 组件、页面、状态管理和父子组件传参。
- 聊天渲染、历史消息、知识库来源展示和反馈按钮。
- 前端格式化、筛选、来源映射等 helper。
- 生产问题修复后的回归测试。
- 前端发布后的 smoke test。

## 2. 前端改动清单

- 纯函数：为 formatter、filter、source mapping 等 helper 添加或更新聚焦测试。
- 组件使用：验证组件确实调用了 helper，或渲染了用户可见的预期状态。
- 父组件传参：新增 Vue `required` prop 时，必须测试父组件把该 prop 传给子组件。
- 历史数据：检查历史会话、已有 API 数据、已保存消息等旧数据渲染，不只测新建状态。
- 构建检查：涉及前端行为或组件契约变化时，必须运行生产构建。

示例：如果 `ChatView` 新增了必需 prop，除了测试 helper 本身，还要测试 `WorkspaceView` 把该 prop 传入 `ChatView`。只测 formatter 不够。

## 3. 必跑前端命令

在 `frontend/` 目录运行：

```bash
npm.cmd test
npm.cmd run build
```

如果 PowerShell 执行策略拦截 `npm`，使用 `npm.cmd`。

## 4. 后端测试与数据库串行规则

后端快速测试：

```powershell
.\.venv\Scripts\python.exe run_tests.py --group fast
```

依赖 `TEST_DATABASE_URL` 的测试组会重置同一个 PostgreSQL 测试库。`database`、`vector`、`api` 必须串行运行，不要在多个终端或并行工具中同时执行，否则会在 `TRUNCATE`、`CREATE TABLE`、`ALTER TABLE` 等 DDL 阶段触发 PostgreSQL deadlock。

推荐用脚本的串行入口一次跑完：

```powershell
.\.venv\Scripts\python.exe run_tests.py --groups database vector api
```

如果只需要单独验证某一层，也可以逐条执行：

```powershell
.\.venv\Scripts\python.exe run_tests.py --group database
.\.venv\Scripts\python.exe run_tests.py --group vector
.\.venv\Scripts\python.exe run_tests.py --group api
```

## 5. 生产发布后 Smoke Test

前端变更部署到生产后，用浏览器检查：

1. 登录成功。
2. 聊天页不是空白屏。
3. 最近一条历史会话可以打开。
4. 用户消息和助手消息正常渲染。
5. 知识库来源卡片只显示答案正文实际引用的来源。
6. 反馈按钮可见，点击或展示时不破坏页面。
7. 浏览器 Console 没有红色运行时错误。
8. 后端和 Nginx 容器仍然健康。

服务器辅助检查：

```bash
docker compose --env-file .env.prod -f compose.prod.yml ps
docker logs ai-agent-backend --tail 100
docker logs ai-agent-nginx --tail 100
```

## 6. 生产问题回归规则

如果生产问题已经到达浏览器或用户侧，修复时必须补一条会在修复前失败的回归测试。

- helper 行为缺失：测 helper。
- 组件行为缺失：测组件模板或组件源码。
- 父子组件传参缺失：测父组件是否传入必需 prop。
- 部署流程缺失：补发布清单、预检脚本或健康检查。

优先选择最小、最稳定、能准确复现问题的自动化测试。

修复后还要做一次轻量复盘，并把结论交给用户确认：

1. 问题为何发生。
2. 为什么现有测试、文档、脚本或流程没有提前发现。
3. 是否缺少 `docs/` 细则、自动化测试、预检脚本、CI 检查或发布清单。
4. 建议补哪一种防线，以及为什么选择它。
5. 用户确认后，再把稳定规则写入文档、测试、脚本或配置。

## 7. Markdown 与中文编码

- 所有 Markdown 文档使用简体中文。
- 文件按 UTF-8 保存，不添加本机专用编码或编辑器私有格式。
- 修改中文文档后，用 UTF-8 读回确认内容正常。
- 如果终端显示乱码，先用 UTF-8 读取文件确认，不要直接判断文件损坏。

## 8. 测试策略演进

技术和工具会变化。发现现有测试策略可能落后时，不要直接大改，先给出建议让用户确认。

建议应包含：

1. 当前做法的限制。
2. 新方案是什么，例如组件测试、端到端测试、可视化回归、契约测试、CI 门禁或发布后自动 smoke test。
3. 新方案能防住哪类问题。
4. 引入成本和维护成本。
5. 适合立即做、稍后做，还是暂缓。
