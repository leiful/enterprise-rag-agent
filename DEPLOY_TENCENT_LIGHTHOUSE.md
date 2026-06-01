# 腾讯轻量云部署攻略

这份文档记录如何把本项目部署到腾讯云轻量应用服务器。当前流程适用于 Ubuntu 24.04，并使用：

```text
Nginx 托管前端 dist
systemd 常驻运行 FastAPI 后端
SQLite 保存用户和 session
Gitee 作为国内服务器拉代码的仓库
```

## 部署结构

公网访问路径：

```text
浏览器
  -> http://服务器公网 IP
  -> Nginx 80 端口
  -> frontend/dist 静态文件
```

接口访问路径：

```text
浏览器 /api/*
  -> Nginx
  -> http://127.0.0.1:8000/*
  -> FastAPI 后端
```

后端只监听服务器本机：

```text
127.0.0.1:8000
```

不要把 `8000` 和 `5173` 暴露到公网。

## 腾讯云防火墙

当前放行：

```text
22    SSH 登录
80    HTTP 访问
ICMP  Ping，可选
```

暂时不要放行：

```text
8000  FastAPI 后端端口
5173  Vite 开发端口
```

以后配置 HTTPS 时，再放行：

```text
443
```

## 代码仓库

因为国内服务器访问 GitHub 可能不稳定，本项目使用 Gitee 作为部署拉取源。

本地有两个 remote：

```text
origin  GitHub
gitee   Gitee
```

本地提交后推送两个仓库：

```powershell
git push origin main
git push gitee main
```

服务器从 Gitee 拉代码。

## 首次部署

登录服务器：

```powershell
ssh ubuntu@服务器公网IP
```

进入部署目录：

```bash
cd /opt
```

从 Gitee 克隆代码：

```bash
sudo git clone https://gitee.com/leiful/ai-tool-calling-agent.git
sudo chown -R ubuntu:ubuntu ai-tool-calling-agent
cd ai-tool-calling-agent
```

确认目录：

```bash
pwd
ls
git log --oneline -5
```

期望目录：

```text
/opt/ai-tool-calling-agent
```

## 后端配置

在项目根目录创建 `.env`：

```bash
nano .env
```

内容示例：

```env
DEEPSEEK_API_KEY=你的真实模型密钥
APP_USERNAME=admin
APP_PASSWORD=你的登录密码
SESSION_MAX_AGE_SECONDS=604800
DATABASE_FILE=/opt/ai-tool-calling-agent/agent.db
```

保存后收紧权限：

```bash
chmod 600 .env
ls -la .env
```

期望权限：

```text
-rw-------
```

## 后端依赖和测试

创建虚拟环境：

```bash
python3 -m venv .venv
```

安装依赖：

```bash
./.venv/bin/python -m pip install -r backend/requirements.txt
```

运行测试：

```bash
./.venv/bin/python run_tests.py
```

期望结果：

```text
Ran ... tests
OK
```

## 前端构建

进入前端目录：

```bash
cd frontend
```

安装依赖：

```bash
npm install
```

创建生产环境前端配置：

```bash
printf "VITE_API_BASE=/api\n" > .env
```

构建：

```bash
npm run build
cd ..
```

构建产物：

```text
frontend/dist/
```

Nginx 托管的是 `frontend/dist/`，不是 `frontend/src/`。

## systemd 后端服务

创建服务文件：

```bash
sudo nano /etc/systemd/system/ai-agent.service
```

内容：

```ini
[Unit]
Description=AI Tool Calling Agent FastAPI backend
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/opt/ai-tool-calling-agent/backend
EnvironmentFile=/opt/ai-tool-calling-agent/.env
ExecStart=/opt/ai-tool-calling-agent/.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

启动并设置开机自启：

```bash
sudo systemctl daemon-reload
sudo systemctl enable ai-agent
sudo systemctl start ai-agent
sudo systemctl status ai-agent
```

看到下面状态表示后端正常：

```text
Active: active (running)
```

测试后端：

```bash
curl http://127.0.0.1:8000/health
```

期望结果：

```json
{"status":"ok","error":null}
```

查看后端日志：

```bash
journalctl -u ai-agent -f
```

## Nginx 配置

创建站点配置：

```bash
sudo nano /etc/nginx/sites-available/ai-agent
```

内容：

```nginx
server {
    listen 80;
    server_name _;

    root /opt/ai-tool-calling-agent/frontend/dist;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

启用配置：

```bash
sudo ln -s /etc/nginx/sites-available/ai-agent /etc/nginx/sites-enabled/ai-agent
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

测试前端：

```bash
curl http://127.0.0.1
```

能看到 HTML，说明 Nginx 静态文件配置正常。

公网访问：

```text
http://服务器公网IP
```

## 日常更新部署

本地修改代码后：

```powershell
git add .
git commit -m "提交说明"
git push origin main
git push gitee main
```

服务器更新代码：

```bash
cd /opt/ai-tool-calling-agent
git pull
```

如果后端代码或依赖变化：

```bash
./.venv/bin/python -m pip install -r backend/requirements.txt
sudo systemctl restart ai-agent
sudo systemctl status ai-agent
```

如果前端代码变化：

```bash
cd frontend
npm install
npm run build
cd ..
sudo systemctl reload nginx
```

如果 `.env` 变化：

```bash
sudo systemctl restart ai-agent
```

## 常用排查命令

后端服务状态：

```bash
sudo systemctl status ai-agent
```

后端实时日志：

```bash
journalctl -u ai-agent -f
```

后端健康检查：

```bash
curl http://127.0.0.1:8000/health
```

Nginx 配置检查：

```bash
sudo nginx -t
```

Nginx 重载：

```bash
sudo systemctl reload nginx
```

查看端口监听：

```bash
ss -tulpn
```

## 当前限制

当前部署是 HTTP：

```text
http://服务器公网IP
```

下一步建议配置：

```text
域名
HTTPS
443 防火墙
Secure cookie
```

正式公网环境不要长期只使用 HTTP 登录。
