# AI Tool Calling Agent

This project is a learning AI Agent with:

- Python tool calling logic
- FastAPI backend
- Vue 3 frontend
- unittest coverage

## Structure

```text
backend/
  AI_agent.py          Agent loop and tool-call execution
  tools.py             Tool functions and tool schemas
  memory.py            History and log helpers
  config.py            Local constants and .env loading
  main.py              FastAPI app
  requirements.txt     Backend dependencies
  tests/               Backend tests

frontend/
  src/                 Vue 3 app
  package.json         Frontend dependencies and scripts

run_tests.py           Runs backend unit tests
.env.example           Local environment template
frontend/.env.example  Frontend environment template
```

## Setup

Create `.env` in the project root. `DEEPSEEK_API_KEY` is used by the backend to call
the model provider. `APP_API_KEY` protects backend API routes such as `/chat` and
`/files`.

```env
DEEPSEEK_API_KEY=your_api_key_here
APP_API_KEY=change_this_local_api_key
```

Create `frontend/.env` with the same app API key:

```env
VITE_API_BASE=http://localhost:8000
VITE_APP_API_KEY=change_this_local_api_key
```

Install backend dependencies:

```bash
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
```

Install frontend dependencies:

```bash
cd frontend
npm.cmd install --cache .npm-cache
```

## Run Tests

From the project root:

```bash
.\.venv\Scripts\python.exe run_tests.py
```

Build the frontend:

```bash
cd frontend
npm.cmd run build
```

## Run Backend

From the project root:

```bash
cd backend
..\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```text
http://localhost:8000/health
```

## Run Frontend

From `frontend/`:

```bash
npm.cmd run dev
```

Open:

```text
http://localhost:5173
```

## API Protection

The browser app sends the frontend value `VITE_APP_API_KEY` as an `X-API-Key`
request header. The backend compares that header with `APP_API_KEY`.

Requests without the correct key are rejected:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/chat `
  -ContentType 'application/json' `
  -Body '{"message":"hello"}'
```

Expected result:

```text
{"detail":"Invalid or missing API key."}
```

Requests with the correct key are allowed:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/chat `
  -Headers @{ 'X-API-Key' = 'change_this_local_api_key' } `
  -ContentType 'application/json' `
  -Body '{"message":"hello"}'
```

## Notes

- `.env`, chat history, chat logs, frontend build output, and dependency folders are ignored by Git.
- `APP_API_KEY` and `VITE_APP_API_KEY` must match in local development.
- Frontend environment variables prefixed with `VITE_` are visible in browser code, so this API key is only a first layer for learning or small local deployments.
- Dangerous file tools require confirmation in the CLI flow.
- `/health` is public so deployments can check whether the backend is running.
