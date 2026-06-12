# Frontend Maintenance And Production Readiness Design

## Goal

Reduce the maintenance load in the Vue frontend, add lightweight frontend validation, and document production readiness checks without changing the current user-facing behavior.

## Scope

- Split focused helper logic out of `frontend/src/App.vue`.
- Add frontend tests for low-level helpers and composables.
- Add a production readiness checklist under `docs/`.

## Non-Goals

- Do not redesign the UI.
- Do not change backend API contracts.
- Do not add new runtime dependencies.
- Do not restructure all frontend views in one pass.

## Approach

This change starts with low-risk extraction. `App.vue` keeps owning the page template and top-level state, while repeated admin loading and reset helpers move into focused modules that can be tested independently. Frontend tests use Node's built-in test runner so the project avoids extra package installation.

## Frontend Split

Create a small admin helper module for sequencing admin data loads and resetting admin-only state on logout. This removes repeated orchestration from `checkSession`, `login`, and `logout` while keeping all existing state refs in `App.vue`.

## Frontend Validation

Add tests for:

- Pagination behavior.
- Formatter fallbacks and labels.
- Model usage calculations.
- Admin helper sequencing and reset behavior.

Add `npm run test` for the frontend and keep `npm run build` as the production bundle check.

## Production Readiness Checklist

Create a concise checklist covering:

- Secrets and environment variables.
- HTTPS, cookies, and CORS.
- PostgreSQL and Chroma backup boundaries.
- Logs and audit data.
- RAG evaluation gates.
- Deployment and rollback checks.

## Verification

- Run frontend tests with `npm.cmd run test`.
- Run frontend production build with `npm.cmd run build`.
- Run backend tests with `.\.venv\Scripts\python.exe run_tests.py`.
