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
```

## Setup

Create `.env` in the project root:

```env
DEEPSEEK_API_KEY=your_api_key_here
```

Install backend dependencies:

```bash
python -m pip install -r backend/requirements.txt
```

Install frontend dependencies:

```bash
cd frontend
npm install
```

## Run Tests

From the project root:

```bash
python run_tests.py
```

## Run Backend

From the project root:

```bash
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```text
http://localhost:8000/health
```

## Run Frontend

From `frontend/`:

```bash
npm run dev
```

Open:

```text
http://localhost:5173
```

## Notes

- `.env`, chat history, chat logs, frontend build output, and dependency folders are ignored by Git.
- Dangerous file tools require confirmation in the CLI flow.
- The first Web version exposes a simple `/chat` endpoint. Browser-based confirmation can be added later.
