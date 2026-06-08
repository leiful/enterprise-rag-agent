# Engineering Notes

This file is a maintenance checklist for the local enterprise RAG project. It
should describe the current architecture, not historical setup details.

## Current Architecture

```text
backend/        FastAPI API, agent runtime, RAG chains, indexing, auth, tests
frontend/       Vue 3 browser UI
knowledge_files/ Uploaded local knowledge files
chroma_db/      Local Chroma persistence directory
rag_eval/       Sample documents, questions, and evaluation reports
scripts/        RAG evaluation and index maintenance scripts
```

The backend uses PostgreSQL for application metadata and Chroma for persistent
vector storage. PostgreSQL stores users, sessions, conversations, messages,
knowledge document metadata, vector chunk metadata, BM25 indexes, knowledge
sources, index jobs, RAG feedback, and access audit records.

## Runtime Configuration

Backend configuration is loaded from the project root `.env`.

Important settings:

```env
DEEPSEEK_API_KEY=your_model_provider_key
APP_ENV=development
EMBEDDING_API_KEY=your_embedding_provider_key
DATABASE_URL=postgresql://user:password@localhost:5432/ai_agent
TEST_DATABASE_URL=postgresql://user:password@localhost:5432/ai_agent_test
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

Frontend configuration lives in `frontend/.env`:

```env
VITE_API_BASE=http://localhost:8000
```

Do not put real API keys or passwords in frontend `VITE_` variables. Frontend
environment variables are bundled into browser-visible code.

## Local Development

Install backend dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Install frontend dependencies:

```powershell
cd frontend
npm.cmd install --cache .npm-cache
```

Run the backend:

```powershell
cd "E:\Project\AI Agent\backend"
..\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Run the frontend:

```powershell
cd "E:\Project\AI Agent\frontend"
npm.cmd run dev
```

Local ports:

```text
Backend:  http://localhost:8000
Frontend: http://localhost:5173
```

## Tests And Build

Run backend tests from the project root:

```powershell
.\.venv\Scripts\python.exe run_tests.py
```

Database integration tests require `TEST_DATABASE_URL` to point at a dedicated
test PostgreSQL database. The test runner may truncate application tables in
that database, so never point it at production data.

Build the frontend:

```powershell
cd frontend
npm.cmd run build
```

## RAG Pipeline

The enterprise RAG path currently includes:

- File upload or local source sync.
- Document parsing for text, Markdown, PDF, DOCX, CSV, and Excel.
- Chunking with heading-aware splitting and optional semantic chunking.
- Embedding through an OpenAI-compatible embedding API.
- Chroma vector persistence.
- PostgreSQL chunk metadata and BM25 index storage.
- Hybrid vector plus BM25 retrieval.
- Optional query rewrite, multi-query expansion, and rerank.
- Department-aware access filtering.
- Lifecycle filtering by effective and expiry dates.
- RAG access auditing and user feedback collection.

The operational status endpoint is:

```text
GET /admin/rag/status
```

The latest local evaluation report endpoint is:

```text
GET /admin/rag/eval
```

The admin operation audit endpoint is:

```text
GET /admin/audit
```

## Knowledge Sources

Registered knowledge sources are stored in PostgreSQL. The default local source
is created on startup when no source exists. Syncing a source queues indexing
jobs for changed files, skips unchanged files, and removes index entries for
files that disappeared from the source folder.

The default local source path is controlled by `DEFAULT_KNOWLEDGE_SOURCE_PATH`
and falls back to the project `knowledge_files/` directory when the setting is
omitted.

Current source support is local-folder based. Future enterprise connectors can
extend this layer for object storage, Confluence, SharePoint, Feishu, or other
document systems.

## Auth And Security

The browser app logs in through `/login`. The backend stores sessions in
PostgreSQL and sends the browser an `HttpOnly` session cookie. Protected routes
require that cookie.

For production deployments:

- Use HTTPS.
- Set `APP_ENV=production`.
- Set `SESSION_COOKIE_SECURE=true`.
- Set `CORS_ALLOW_LOCALHOST_REGEX=false`.
- Restrict `CORS_ALLOWED_ORIGINS` to the real frontend origin.
- Use strong admin credentials.
- Keep `.env`, Chroma data, PostgreSQL data, logs, and uploaded knowledge files
  out of public static hosting.
- Treat model API keys and embedding API keys as backend-only secrets.

## Deployment Boundary

Only deploy the frontend build output as static files:

```text
frontend/dist/
```

Do not expose these paths as public static content:

```text
.env
backend/
frontend/src/
frontend/node_modules/
knowledge_files/
chroma_db/
logs/
```

The backend should run as a server process behind a reverse proxy or platform
service manager.

## Change Checklist

Before editing, identify the affected layer:

```text
backend
frontend
configuration
tests
documentation
deployment
```

After editing:

- Run the narrowest relevant tests.
- Run the full backend test suite for auth, database, indexing, or RAG changes.
- Build the frontend when UI code changes.
- Update README or this file when startup, configuration, schema, or deployment
  behavior changes.
- Check `git diff` before committing.
