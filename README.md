# Enterprise RAG Agent

Local enterprise RAG assistant and operations console.

## What It Includes

- FastAPI backend with login-protected chat and conversation history.
- Vue 3 frontend for chat, knowledge management, users, operations, and token monitoring.
- PostgreSQL metadata storage for users, sessions, conversations, knowledge metadata, audit events, feedback, and model usage.
- Chroma vector persistence with PostgreSQL chunk metadata and BM25 hybrid retrieval.
- Knowledge upload, local source sync, indexing jobs, deduplication, access control, and RAG evaluation.

## Project Layout

```text
backend/       FastAPI app, routes, services, RAG chains, database helpers, tests
frontend/      Vue 3 browser app
scripts/       RAG evaluation and maintenance scripts
rag_eval/      Evaluation questions and generated reports
knowledge_files/ Local knowledge source files, ignored by Git
chroma_db/     Local Chroma persistence directory, ignored by Git
compose.yml    Local PostgreSQL service for development
run_tests.py   Backend unittest runner
```

## Local Architecture

For local development, keep the application code on Windows and run PostgreSQL in Docker:

```text
Windows:
  backend, frontend, .venv, npm, .env, knowledge_files, chroma_db

Docker:
  PostgreSQL container ai-agent-postgres
  PostgreSQL volume aiagent_ai_agent_postgres_data
```

The backend connects to PostgreSQL through `localhost:5432`.

## Start PostgreSQL

From the project root:

```powershell
docker compose up -d
```

Check the container:

```powershell
docker ps
```

Open the main database:

```powershell
docker exec -it ai-agent-postgres psql -U ai_agent_user -d ai_agent
```

Exit `psql` with:

```sql
\q
```

Create the test database once:

```powershell
docker exec -it ai-agent-postgres psql -U ai_agent_user -d postgres
```

```sql
CREATE USER ai_agent_test_user WITH PASSWORD '123456';
CREATE DATABASE ai_agent_test OWNER ai_agent_test_user;
GRANT ALL PRIVILEGES ON DATABASE ai_agent_test TO ai_agent_test_user;
\q
```

Use a stronger local password when keeping data long term. If a Docker volume already exists, changing `POSTGRES_PASSWORD` in `compose.yml` does not change the existing database password; use `ALTER USER` in PostgreSQL and update `.env`.

## Environment

Create `.env` in the project root. Real secrets belong only in backend environment variables.

```env
DEEPSEEK_API_KEY=your_api_key_here
APP_ENV=development
EMBEDDING_API_KEY=your_dashscope_api_key_here
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_MODEL=text-embedding-v4
DATABASE_URL=postgresql://ai_agent_user:123456@localhost:5432/ai_agent
TEST_DATABASE_URL=postgresql://ai_agent_test_user:123456@localhost:5432/ai_agent_test
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

Create `frontend/.env`:

```env
VITE_API_BASE=http://localhost:8000
```

## Install Dependencies

Backend:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Frontend:

```powershell
cd frontend
npm.cmd install --cache .npm-cache
```

## Run The App

Backend:

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
cd frontend
npm.cmd run dev
```

Open:

```text
http://localhost:5173
```

Health check:

```text
http://localhost:8000/health
```

## Run Tests

Fast backend tests:

```powershell
.\.venv\Scripts\python.exe run_tests.py --group fast
```

Database-backed test groups must be run serially because they reset the same `ai_agent_test` database:

```powershell
.\.venv\Scripts\python.exe run_tests.py --group database
.\.venv\Scripts\python.exe run_tests.py --group vector
.\.venv\Scripts\python.exe run_tests.py --group api
```

Frontend:

```powershell
cd frontend
npm.cmd test
npm.cmd run build
```

If `TEST_DATABASE_URL` is missing or unreachable, PostgreSQL integration tests are skipped. The test database is truncated during integration tests, so never point `TEST_DATABASE_URL` at real application data.

## Common Operations

RAG status:

```text
GET /admin/rag/status
```

Admin audit:

```text
GET /admin/audit
```

Latest local RAG evaluation report:

```text
GET /admin/rag/eval
```

Run the local RAG evaluation script after starting the backend:

```powershell
.\.venv\Scripts\python.exe scripts\rag_eval.py
```

## Production Notes

- Set `APP_ENV=production`.
- Use HTTPS.
- Set `SESSION_COOKIE_SECURE=true`.
- Set `CORS_ALLOW_LOCALHOST_REGEX=false`.
- Restrict `CORS_ALLOWED_ORIGINS` to the production frontend origin.
- Use strong application and database passwords.
- Deploy only `frontend/dist/` as static frontend content.
- Do not expose `.env`, `backend/`, `frontend/src/`, `knowledge_files/`, `chroma_db/`, `logs/`, or PostgreSQL data as public static files.

See `ENGINEERING_NOTES.md` for architecture and maintenance details.
