# Backend Route Split Design

## Goal

Reduce the size and coupling of `backend/main.py` without changing API behavior. The first optimization phase moves FastAPI routes and route-local helpers into focused modules while keeping startup, middleware, CORS, and app construction in `main.py`.

## Scope

This phase covers the backend route split only. It does not change frontend structure, vector database tracking, database schemas, request paths, response models, authentication behavior, or RAG behavior.

Frontend component splitting and repository data cleanup are separate follow-up phases.

## Recommended Approach

Use a low-risk router split:

- Keep `backend/main.py` responsible for creating the FastAPI app, configuring middleware, defining lifespan startup, and registering routers.
- Add shared runtime modules so route files do not import mutable state from `main.py`.
- Move existing route functions into `backend/routes/` by domain.
- Preserve all existing endpoint paths and dependencies.

This approach gives immediate maintainability gains while minimizing behavior risk.

## Architecture

Create these modules:

- `backend/app_state.py`: model client, startup error, config issues, session cookie name, chat admission counters, and chat concurrency helpers.
- `backend/dependencies.py`: authentication and authorization dependencies, session creation helpers, current user lookup, department scope helpers, and request/client helpers.
- `backend/routes/auth.py`: `/login`, `/logout`, and `/me`.
- `backend/routes/chat.py`: conversation endpoints, `/chat`, and `/chat/stream`.
- `backend/routes/knowledge.py`: knowledge file listing, upload, index jobs, document management, source sync, deduplication, audit search, and `/knowledge/search`.
- `backend/routes/admin.py`: admin RAG status, model usage, users, departments, audit, and feedback endpoints.
- `backend/routes/rag_eval.py`: RAG evaluation suite listing, latest report, and run endpoint.

`backend/main.py` will import and include these routers. It may keep pure app-level helpers such as CORS setup, request logging middleware, security header injection, health check wiring, and startup initialization.

## Data Flow

Requests enter the same FastAPI app. Route modules use dependencies from `backend/dependencies.py` for login, admin checks, session cookies, and user department scope. Route modules read and update shared runtime state through `backend/app_state.py`, especially the model client and chat admission counters.

The existing database, vector store, RAG chain, model usage, and knowledge modules remain the authoritative implementation for behavior.

## Error Handling

Existing `HTTPException` status codes and response details should be preserved. The split should not introduce broad exception swallowing. Any helper moved from `main.py` should keep its current behavior and logging.

## Testing

Before moving production code, add a small test that verifies the expected route set remains registered after app construction. Then move routes module by module and keep the existing test suite green.

Verification commands:

- `.\.venv\Scripts\python.exe run_tests.py --group fast`
- `.\.venv\Scripts\python.exe run_tests.py`
- `npm.cmd run build` from `frontend/`

## Success Criteria

- Existing public API paths still exist.
- Existing auth/admin behavior is unchanged.
- Existing backend tests pass.
- Frontend production build still passes.
- `backend/main.py` becomes materially smaller and primarily app-composition focused.
