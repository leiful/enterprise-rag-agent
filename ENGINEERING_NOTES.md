# 工程开发笔记

这个文件是给自己看的工程开发自查清单，用来记录这个项目在开发、测试、构建、配置和部署时要注意的事情。

## 项目结构

```text
backend/   FastAPI 后端、Python 源码、测试、AI Agent 逻辑
frontend/  Vue 3 前端、Vite 开发和构建工具
.env       后端本地密钥配置，不能提交到 Git
```

后端通常直接运行 Python 源码。前端需要构建成浏览器可运行的文件，输出目录是 `frontend/dist/`。

## 依赖环境

后端依赖安装到 Python 虚拟环境 `.venv`：

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

前端依赖安装到 `frontend/node_modules`：

```powershell
cd frontend
npm.cmd install --cache .npm-cache
```

除非有明确原因，不要把项目依赖安装到全局环境里。

## 配置文件

后端配置在项目根目录的 `.env`：

```env
DEEPSEEK_API_KEY=your_model_provider_key
APP_API_KEY=your_local_app_api_key
```

前端配置在 `frontend/.env`：

```env
VITE_API_BASE=http://localhost:8000
VITE_APP_API_KEY=your_local_app_api_key
```

本地开发时，`APP_API_KEY` 和 `VITE_APP_API_KEY` 的值必须一致。

真实密钥不能提交到 Git。`.env` 文件已经被 `.gitignore` 忽略。

## 端口

当前本地端口：

```text
后端: http://localhost:8000
前端: http://localhost:5173
```

如果端口被占用，要么停止旧进程，要么有意识地换端口，并同步修改相关配置。

## 本地运行

后端用一个终端运行：

```powershell
cd "E:\Project\AI Agent\backend"
..\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

前端用另一个终端运行：

```powershell
cd "E:\Project\AI Agent\frontend"
npm.cmd run dev
```

开发时要保持两个终端都在运行。前端开发服务器会调用后端 API。

## 测试

测试用来检查后端行为在修改代码后是否仍然正确。

从项目根目录运行：

```powershell
.\.venv\Scripts\python.exe run_tests.py
```

期望结果：

```text
Ran ... tests
OK
```

修改后端、接口鉴权、工具逻辑、记忆逻辑、文件操作逻辑后，都应该跑测试。

## 构建

构建用来检查前端能不能被正确编译和打包，并生成部署用文件。

从 `frontend/` 目录运行：

```powershell
npm.cmd run build
```

构建产物输出到：

```text
frontend/dist/
```

正式部署前端时，部署 `frontend/dist/`，不要部署整个 `frontend/` 文件夹，也不要部署项目根目录。

## API 保护

后端 `/chat` 和 `/files` 这类接口需要请求头：

```text
X-API-Key: APP_API_KEY 的值
```

`/health` 保持公开，用来让部署平台或自己检查后端是否运行。

测试不带密钥访问：

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/chat `
  -ContentType 'application/json' `
  -Body '{"message":"hello"}'
```

期望结果：

```text
Invalid or missing API key.
```

注意：前端里所有 `VITE_` 开头的变量都会被打包进浏览器代码里，用户可以看到。所以现在这个 API Key 适合学习、本地开发、小范围保护，但不是完整的公网登录系统。

## 部署边界

不要把这些内容作为静态文件暴露出去：

```text
.env
README.md
backend/
frontend/src/
frontend/node_modules/
frontend/.env
```

前端部署时，只暴露：

```text
frontend/dist/
```

后端部署时，用服务器进程运行 FastAPI 应用。不要把 `backend/` 文件夹当作静态目录给别人下载。

## 开发习惯

改代码之前先判断这次改动属于哪一层：

```text
后端
前端
配置
测试
文档
部署
```

改完代码之后：

```text
运行相关验证
查看 git diff
如果启动方式、配置方式、部署方式变了，同步更新 README 或工程笔记
```

提交之前：

```powershell
git status
git diff
```

每次提交尽量小而完整。一个好的工程改动，通常会同时考虑代码、测试和文档。
