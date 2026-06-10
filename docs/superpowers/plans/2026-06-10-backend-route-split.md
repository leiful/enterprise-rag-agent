# Backend Route Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `backend/main.py` into focused FastAPI route modules without changing public API behavior.

**Architecture:** Keep `main.py` as the app composition layer. Move shared mutable runtime state to `app_state.py`, request dependencies to `dependencies.py`, and route handlers to domain modules under `backend/routes/`.

**Tech Stack:** Python 3, FastAPI, unittest, existing project test runner.

---

## File Structure

- Create `backend/app_state.py`: shared model client state, startup error state, config issue list, session cookie name, and chat admission counters.
- Create `backend/dependencies.py`: authentication helpers, admin dependency, session helper, user department helper, login throttling helpers, and client IP helper.
- Create `backend/routes/__init__.py`: route package marker.
- Create `backend/routes/auth.py`: login/logout/me endpoints.
- Create `backend/routes/admin.py`: admin health/status/model usage/users/departments/audit/feedback endpoints.
- Create `backend/routes/rag_eval.py`: RAG evaluation endpoints.
- Create `backend/routes/chat.py`: conversation and chat endpoints.
- Create `backend/routes/knowledge.py`: knowledge file, indexing, source, document, and search endpoints.
- Modify `backend/main.py`: import shared state and routers, include routers, remove moved route functions.
- Modify `backend/tests/test_main_api.py`: add route registration coverage.

## Task 1: Add Route Registration Test

**Files:**
- Modify: `backend/tests/test_main_api.py`

- [ ] **Step 1: Write the failing route registration test**

Add this test method to `ApiAuthTests`:

```python
    def test_expected_routes_are_registered(self):
        registered_paths = {route.path for route in main.app.routes}

        expected_paths = {
            "/health",
            "/login",
            "/logout",
            "/me",
            "/admin/rag/status",
            "/admin/model-usage",
            "/admin/rag/eval",
            "/admin/rag/eval/suites",
            "/admin/rag/eval/run",
            "/admin/feedback",
            "/admin/users",
            "/admin/departments",
            "/conversations",
            "/conversations/{conversation_id}/messages",
            "/feedback",
            "/chat",
            "/chat/stream",
            "/files",
            "/knowledge/index-file",
            "/knowledge/upload",
            "/knowledge/index-jobs/{job_id}",
            "/knowledge/index-jobs/acknowledge-failed",
            "/knowledge/documents",
            "/knowledge/documents/{document_id}",
            "/knowledge/reindex",
            "/knowledge/sources",
            "/knowledge/sources/{source_id}/sync",
            "/knowledge/sources/missing-files",
            "/knowledge/documents/deduplicate",
            "/admin/knowledge-audit",
            "/admin/audit",
            "/knowledge/search",
        }

        self.assertTrue(expected_paths <= registered_paths)
```

- [ ] **Step 2: Run test to verify baseline**

Run:

```powershell
.\.venv\Scripts\python.exe run_tests.py test_main_api.ApiAuthTests.test_expected_routes_are_registered
```

Expected: PASS before refactor, proving the test captures current route registration.

## Task 2: Extract Shared App State

**Files:**
- Create: `backend/app_state.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Move state and chat admission into `app_state.py`**

Create:

```python
# -*- coding: utf-8 -*-

from collections import Counter
import threading

from fastapi import HTTPException, status

from config import (
    CHAT_MAX_CONCURRENT_PER_CONVERSATION,
    CHAT_MAX_CONCURRENT_PER_USER,
    CHAT_MAX_CONCURRENT_REQUESTS,
)


client = None
startup_error = None
config_issues = []
SESSION_COOKIE = "agent_session"

chat_admission_lock = threading.Lock()
active_chat_total = 0
active_chat_by_user = Counter()
active_chat_by_conversation = Counter()


class ChatAdmission:
    def __init__(self, user_id, conversation_id):
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.acquired = False

    def __enter__(self):
        global active_chat_total
        with chat_admission_lock:
            if active_chat_total >= CHAT_MAX_CONCURRENT_REQUESTS:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Chat is busy. Please try again shortly.",
                    headers={"Retry-After": "5"},
                )
            if active_chat_by_user[self.user_id] >= CHAT_MAX_CONCURRENT_PER_USER:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="You already have a chat request running. Please wait for it to finish.",
                    headers={"Retry-After": "5"},
                )
            if active_chat_by_conversation[self.conversation_id] >= CHAT_MAX_CONCURRENT_PER_CONVERSATION:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="This conversation is already answering another message.",
                    headers={"Retry-After": "5"},
                )

            active_chat_total += 1
            active_chat_by_user[self.user_id] += 1
            active_chat_by_conversation[self.conversation_id] += 1
            self.acquired = True
        return self

    def __exit__(self, exc_type, exc, traceback):
        global active_chat_total
        if not self.acquired:
            return
        with chat_admission_lock:
            active_chat_total = max(0, active_chat_total - 1)
            active_chat_by_user[self.user_id] -= 1
            active_chat_by_conversation[self.conversation_id] -= 1
            if active_chat_by_user[self.user_id] <= 0:
                del active_chat_by_user[self.user_id]
            if active_chat_by_conversation[self.conversation_id] <= 0:
                del active_chat_by_conversation[self.conversation_id]


def current_chat_admission_status():
    with chat_admission_lock:
        return {
            "active": active_chat_total,
            "max_concurrent": CHAT_MAX_CONCURRENT_REQUESTS,
            "max_per_user": CHAT_MAX_CONCURRENT_PER_USER,
            "max_per_conversation": CHAT_MAX_CONCURRENT_PER_CONVERSATION,
        }
```

- [ ] **Step 2: Update `main.py` imports and references**

Replace local definitions of `client`, `startup_error`, `config_issues`, `SESSION_COOKIE`, `ChatAdmission`, and `current_chat_admission_status` with `import app_state`.

Use `app_state.client`, `app_state.startup_error`, `app_state.config_issues`, `app_state.SESSION_COOKIE`, `app_state.ChatAdmission`, and `app_state.current_chat_admission_status()`.

- [ ] **Step 3: Run focused API tests**

Run:

```powershell
.\.venv\Scripts\python.exe run_tests.py --group api
```

Expected: PASS.

## Task 3: Extract Auth Dependencies and Auth Routes

**Files:**
- Create: `backend/dependencies.py`
- Create: `backend/routes/__init__.py`
- Create: `backend/routes/auth.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Move auth helpers into `dependencies.py`**

Move these functions from `main.py`: `require_auth_config`, `create_session`, `get_session_username`, `require_user`, `require_admin`, `user_knowledge_departments`, `get_client_ip`, `login_failure_key`, `clear_expired_login_failures`, `is_login_locked`, `record_login_failure`, and `clear_login_failures`.

Keep `login_failures = {}` in `dependencies.py`. Import `app_state.SESSION_COOKIE`.

- [ ] **Step 2: Move auth endpoints into `routes/auth.py`**

Move `/login`, `/logout`, and `/me` handlers into `routes/auth.py` with:

```python
from fastapi import APIRouter

router = APIRouter()
```

Use `@router.post` and `@router.get` decorators with the same paths and response models.

- [ ] **Step 3: Register auth router in `main.py`**

Add:

```python
from routes import auth

app.include_router(auth.router)
```

- [ ] **Step 4: Run auth-focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe run_tests.py test_main_api.ApiAuthTests.test_login_accepts_valid_credentials test_main_api.ApiAuthTests.test_logout_clears_session test_main_api.ApiAuthTests.test_me_reports_signed_out_without_session
```

Expected: PASS.

## Task 4: Extract Admin and RAG Eval Routes

**Files:**
- Create: `backend/routes/admin.py`
- Create: `backend/routes/rag_eval.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Move admin status and user management endpoints**

Move `/admin/rag/status`, `/admin/model-usage`, `/admin/feedback`, `/admin/users`, `/admin/departments`, `/admin/knowledge-audit`, and `/admin/audit` handlers into `routes/admin.py`.

- [ ] **Step 2: Move RAG eval endpoints**

Move `/admin/rag/eval`, `/admin/rag/eval/suites`, and `/admin/rag/eval/run` handlers and their helper functions into `routes/rag_eval.py`.

- [ ] **Step 3: Register routers**

Add:

```python
from routes import admin, rag_eval

app.include_router(admin.router)
app.include_router(rag_eval.router)
```

- [ ] **Step 4: Run admin and RAG status tests**

Run:

```powershell
.\.venv\Scripts\python.exe run_tests.py test_main_api.ApiAuthTests.test_admin_can_manage_departments test_main_api.ApiAuthTests.test_health_reports_config_warnings test_rag_status
```

Expected: PASS.

## Task 5: Extract Chat Routes

**Files:**
- Create: `backend/routes/chat.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Move chat helpers and endpoints**

Move `make_conversation_title`, `build_agent_messages`, `encode_sources_header`, `answer_abstained`, `answer_has_citation`, `/conversations`, `/conversations/{conversation_id}/messages`, `/feedback`, `/chat`, and `/chat/stream` into `routes/chat.py`.

Use `app_state.client`, `app_state.startup_error`, and `app_state.ChatAdmission`.

- [ ] **Step 2: Register chat router**

Add:

```python
from routes import chat

app.include_router(chat.router)
```

- [ ] **Step 3: Run chat-focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe run_tests.py test_main_api.ApiAuthTests.test_chat_accepts_logged_in_session test_main_api.ApiAuthTests.test_chat_stream_accepts_logged_in_session test_main_api.ApiAuthTests.test_chat_rejects_when_user_already_has_running_request
```

Expected: PASS.

## Task 6: Extract Knowledge Routes

**Files:**
- Create: `backend/routes/knowledge.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Move knowledge helpers and endpoints**

Move `document_ocr_available`, `project_root`, `search_result_to_source`, `parse_tags_field`, `parse_metadata_field`, `run_index_job`, `enqueue_index_job`, `get_database_health`, `get_rag_operational_status`, `get_deepseek_balance`, `/files`, `/knowledge/index-file`, `/knowledge/upload`, `/knowledge/index-jobs/{job_id}`, `/knowledge/index-jobs/acknowledge-failed`, `/knowledge/documents`, `/knowledge/documents/{document_id}`, `/knowledge/reindex`, `/knowledge/sources`, `/knowledge/sources/{source_id}/sync`, `/knowledge/sources/missing-files`, `/knowledge/documents/deduplicate`, and `/knowledge/search` into `routes/knowledge.py`.

If `get_rag_operational_status` is needed by `routes/admin.py`, import it from `routes.knowledge`.

- [ ] **Step 2: Register knowledge router**

Add:

```python
from routes import knowledge

app.include_router(knowledge.router)
```

- [ ] **Step 3: Run knowledge-focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe run_tests.py test_main_api.ApiAuthTests.test_logged_in_user_can_upload_and_index_knowledge_file test_main_api.ApiAuthTests.test_logged_in_user_can_index_and_search_knowledge_file test_main_api.ApiAuthTests.test_knowledge_search_filters_by_min_score
```

Expected: PASS.

## Task 7: Final Verification

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: Remove unused imports and dead route code from `main.py`**

After all routers are registered, keep `main.py` focused on app construction, startup, middleware, health, and router inclusion.

- [ ] **Step 2: Run full backend suite**

Run:

```powershell
.\.venv\Scripts\python.exe run_tests.py
```

Expected: PASS with all tests.

- [ ] **Step 3: Run frontend build**

Run from `frontend/`:

```powershell
npm.cmd run build
```

Expected: Vite build exits with code 0.
