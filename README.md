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
the model provider. `APP_USERNAME` and `APP_PASSWORD` are used for local login.
`EMBEDDING_API_KEY` is used for vector search embeddings.

```env
DEEPSEEK_API_KEY=your_api_key_here
EMBEDDING_API_KEY=your_dashscope_api_key_here
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_MODEL=text-embedding-v4
APP_USERNAME=admin
APP_PASSWORD=change_this_local_password
SESSION_MAX_AGE_SECONDS=604800
DATABASE_FILE=E:\Project\AI Agent\agent.db
```

Create `frontend/.env`:

```env
VITE_API_BASE=http://localhost:8000
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

## Login Protection

The browser app logs in with `/login`. After a successful login, the backend
creates a random session id, stores it in SQLite, and sends it to the browser as
an `HttpOnly` session cookie. Protected routes such as `/chat` and `/files`
require that session cookie. The default session lifetime is one week
(`SESSION_MAX_AGE_SECONDS=604800`).

The backend creates the SQLite database automatically on startup. By default it
uses `agent.db` in the project root. The database contains:

```text
users      usernames and password hashes
sessions   random session ids, user ids, and expiration times
vector_chunks  document chunks and embedding vectors for vector search
```

## Vector Search

The backend has a small SQLite vector store in `backend/vector_store.py`.
It uses the OpenAI-compatible embeddings API, so Alibaba Cloud Model Studio
works with:

```env
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_MODEL=text-embedding-v4
```

Basic usage from the project root:

```powershell
.\.venv\Scripts\python.exe
```

```python
import sys
sys.path.insert(0, "backend")

import vector_store

vector_store.init_vector_store()
vector_store.upsert_document(
    "agent_intro",
    "AI Agent needs tool calling, memory, planning, and reflection."
)

results = vector_store.search("how to learn agent tools")
for result in results:
    print(result.score, result.document_id, result.text)
```

## RAG Evaluation

The repository includes a small RAG evaluation pack in `rag_eval/`.

```text
rag_eval/sample_docs/   Markdown documents for upload
rag_eval/questions.json Evaluation questions and expected source documents
scripts/rag_eval.py     Uploads docs, asks questions, and writes reports
```

Start the backend first, then run from the project root:

```powershell
.\.venv\Scripts\python.exe scripts\rag_eval.py
```

The script reads `APP_USERNAME` and `APP_PASSWORD` from `.env`, uploads the
sample documents, calls `/knowledge/search` and `/chat`, then writes JSON, CSV,
and Markdown reports under `rag_eval/reports/`.

Useful options:

```powershell
.\.venv\Scripts\python.exe scripts\rag_eval.py --skip-upload
.\.venv\Scripts\python.exe scripts\rag_eval.py --skip-chat
.\.venv\Scripts\python.exe scripts\rag_eval.py --top-k 5 --min-score 0.4
```

Convert a small public RAG benchmark JSONL sample into local eval files:

```powershell
.\.venv\Scripts\python.exe scripts\rag_benchmark_download.py --config emanual --split test --limit 5
.\.venv\Scripts\python.exe scripts\rag_benchmark_prepare.py
.\.venv\Scripts\python.exe scripts\rag_eval.py --docs-dir rag_eval\generated\docs --questions rag_eval\generated\questions.json
```

Requests without a login session are rejected:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/chat `
  -ContentType 'application/json' `
  -Body '{"message":"hello"}'
```

Expected result:

```text
{"detail":"Login required."}
```

Log in and keep the session cookie:

```powershell
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/login `
  -WebSession $session `
  -ContentType 'application/json' `
  -Body '{"username":"admin","password":"change_this_local_password"}'
```

Use the logged-in session:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/chat `
  -WebSession $session `
  -ContentType 'application/json' `
  -Body '{"message":"hello"}'
```

## Notes

- `.env`, chat history, chat logs, frontend build output, and dependency folders are ignored by Git.
- SQLite database files (`*.db`, `*.db-shm`, `*.db-wal`) are ignored by Git.
- Real secrets belong on the backend. Do not put passwords or model API keys in frontend `VITE_` variables.
- Dangerous file tools require confirmation in the CLI flow.
- `/health` is public so deployments can check whether the backend is running.
