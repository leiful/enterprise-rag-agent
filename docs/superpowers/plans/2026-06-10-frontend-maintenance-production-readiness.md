# Frontend Maintenance And Production Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce `App.vue` orchestration weight, add lightweight frontend tests, and document production readiness checks.

**Architecture:** Keep `App.vue` as the top-level Vue shell. Move reusable admin orchestration helpers into `frontend/src/adminLoaders.js`, test pure frontend modules with Node's built-in test runner, and add a deployment checklist in `docs/`.

**Tech Stack:** Vue 3, Vite, Node built-in `node:test`, FastAPI backend unchanged.

---

## File Structure

- Create: `frontend/src/adminLoaders.js` for admin load sequencing and admin state reset helpers.
- Create: `frontend/src/tests/*.test.mjs` for frontend helper tests.
- Modify: `frontend/src/App.vue` to call extracted helpers.
- Modify: `frontend/package.json` to add a `test` script.
- Create: `docs/PRODUCTION_READINESS_CHECKLIST.md` for deploy checks.

### Task 1: Frontend Tests

**Files:**
- Create: `frontend/src/tests/pagination.test.mjs`
- Create: `frontend/src/tests/formatters.test.mjs`
- Create: `frontend/src/tests/useModelUsage.test.mjs`
- Modify: `frontend/package.json`

- [ ] **Step 1: Add failing tests for existing frontend helper behavior**

Add Node tests that import pagination, formatter, and model usage helpers. The tests should initially fail because the project has no frontend test script.

- [ ] **Step 2: Run frontend tests and verify failure**

Run: `npm.cmd run test`

Expected: command fails because the `test` script does not exist.

- [ ] **Step 3: Add the frontend test script**

Add `"test": "node --test src/tests/*.test.mjs"` to `frontend/package.json`.

- [ ] **Step 4: Run frontend tests and verify pass**

Run: `npm.cmd run test`

Expected: all frontend helper tests pass.

### Task 2: Admin Orchestration Extraction

**Files:**
- Create: `frontend/src/adminLoaders.js`
- Create: `frontend/src/tests/adminLoaders.test.mjs`
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Add failing tests for admin helper sequencing**

Add tests that assert admin loaders run in order for admin users, are skipped for non-admin users, and reset helpers clear admin state refs.

- [ ] **Step 2: Run admin helper test and verify failure**

Run: `npm.cmd run test`

Expected: fails because `adminLoaders.js` does not exist.

- [ ] **Step 3: Implement `adminLoaders.js`**

Export `loadAdminDashboard`, `resetAdminState`, and `activateNonAdminChat`. Keep these helpers framework-light: accept refs and callbacks from `App.vue`, mutate only the passed refs, and return promises for load sequencing.

- [ ] **Step 4: Update `App.vue` to use admin helpers**

Replace duplicated admin loading blocks in `checkSession` and `login`. Replace the admin state clearing block in `logout`.

- [ ] **Step 5: Run frontend tests**

Run: `npm.cmd run test`

Expected: all frontend tests pass.

### Task 3: Production Readiness Checklist

**Files:**
- Create: `docs/PRODUCTION_READINESS_CHECKLIST.md`

- [ ] **Step 1: Write the checklist**

Cover environment variables, auth cookies, CORS, database and pgvector backups, logs, RAG evaluation gates, deployment boundaries, and rollback checks.

- [ ] **Step 2: Review for deploy blockers**

Confirm the checklist has no open placeholder text and does not recommend exposing `.env`, `knowledge_files`, `logs`, or backend source as static assets.

### Task 4: Final Verification

**Files:**
- No new files.

- [ ] **Step 1: Run frontend tests**

Run: `npm.cmd run test`

Expected: all tests pass.

- [ ] **Step 2: Run frontend build**

Run: `npm.cmd run build`

Expected: Vite build succeeds.

- [ ] **Step 3: Run backend tests**

Run: `.\.venv\Scripts\python.exe run_tests.py`

Expected: all backend tests pass.
