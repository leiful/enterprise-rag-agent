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
`VECTOR_STORE_BACKEND=chroma` enables the LangChain + Chroma vector backend while
keeping PostgreSQL metadata and BM25 indexes available.

```env
DEEPSEEK_API_KEY=your_api_key_here
APP_ENV=development
EMBEDDING_API_KEY=your_dashscope_api_key_here
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_MODEL=text-embedding-v4
DATABASE_URL=postgresql://ai_agent_user:your_password_here@localhost:5432/ai_agent
TEST_DATABASE_URL=postgresql://ai_agent_test_user:your_password_here@localhost:5432/ai_agent_test
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

Database and API integration tests require `TEST_DATABASE_URL` to point at a
dedicated PostgreSQL test database. The test runner truncates application tables
in that database, so do not point it at production data. Without
`TEST_DATABASE_URL`, PostgreSQL integration tests are skipped while pure unit
tests still run.

Build the frontend:

```bash
cd frontend
npm.cmd run build
```

## Run Backend

From the project root:

```bash
cd backend
..\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

For local debugging with hot reload, use:

```bash
cd backend
..\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
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
creates a random session id, stores it in PostgreSQL, and sends it to the browser as
an `HttpOnly` session cookie. Protected routes such as `/chat` and `/files`
require that session cookie. The default session lifetime is one week
(`SESSION_MAX_AGE_SECONDS=604800`).

The backend initializes its PostgreSQL tables on startup using `DATABASE_URL`.
The database contains:

```text
users      usernames and password hashes
sessions   random session ids, user ids, and expiration times
vector_chunks  document chunks and embedding vectors for vector search
```

For production deployments, set `APP_ENV=production`, use HTTPS, set
`SESSION_COOKIE_SECURE=true`, disable `CORS_ALLOW_LOCALHOST_REGEX`, and restrict
`CORS_ALLOWED_ORIGINS` to the real frontend origin.

## Enterprise RAG Operations

Admins can inspect RAG operating status with:

```text
GET /admin/rag/status
```

Admins can inspect management actions such as user, department, source sync, and
knowledge indexing changes with:

```text
GET /admin/audit
```

The response summarizes document and chunk counts, knowledge source file states,
index job states, BM25 stats, retrieval feature flags, and knowledge access audit
event counts. This is useful for deployment checks and for spotting failed jobs,
unsynced sources, or source files that disappeared.

The default retrieval profile is tuned for enterprise knowledge bases: query
rewrite, multi-query expansion, and reranking are enabled by default; recall is
broadened before rerank; and answer preflight includes document metadata such as
department, sensitivity, owner, version, and effective dates when available.
Deployments can tune this profile in `.env`:

```env
ENABLE_QUERY_REWRITE=true
ENABLE_MULTI_QUERY=true
ENABLE_RERANK=true
RECALL_K=24
DEFAULT_KNOWLEDGE_TOP_K=5
DEFAULT_KNOWLEDGE_MIN_SCORE=0.25
MULTI_QUERY_COUNT=4
HYBRID_BM25_WEIGHT=0.40
HYBRID_VECTOR_WEIGHT=0.60
```

When a registered local knowledge source is synced, files that have disappeared
from the source folder are marked `missing` and their vector/BM25 indexes are
removed so stale enterprise content is no longer returned by RAG.
The startup-created default local source uses `DEFAULT_KNOWLEDGE_SOURCE_PATH`,
which defaults to the project's `knowledge_files/` directory when the setting is
omitted.

## Vector Search

The backend uses LangChain + Chroma persistent vector storage when
`VECTOR_STORE_BACKEND=chroma`. It keeps chunk metadata, BM25 indexes, sessions,
conversations, indexing jobs, knowledge sources, and audit records in
PostgreSQL, so hybrid search and the existing APIs continue to work.
Chroma may create its own `chroma.sqlite3` file under `CHROMA_PERSIST_DIR`; that
file belongs to Chroma's internal storage and is not the application's database.

It uses the OpenAI-compatible embeddings API, so Alibaba Cloud Model Studio
works with:

```env
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_MODEL=text-embedding-v4
VECTOR_STORE_BACKEND=chroma
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
- Chroma persistence output and local database artifacts are ignored by Git.
- Real secrets belong on the backend. Do not put passwords or model API keys in frontend `VITE_` variables.
- Dangerous file tools require confirmation in the CLI flow.
- `/health` is public so deployments can check whether the backend is running.
