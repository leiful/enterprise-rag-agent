# Production Readiness Checklist

Use this checklist before promoting the enterprise RAG agent beyond local or internal test usage.

## Secrets And Environment

- Set `APP_ENV=production`.
- Set strong `APP_USERNAME` and `APP_PASSWORD` values.
- Set `DEEPSEEK_API_KEY` only in the backend runtime environment.
- Set `EMBEDDING_API_KEY` only in the backend runtime environment.
- Keep real secrets out of `frontend/.env` because `VITE_` values are bundled into browser code.
- Keep `.env` out of Git and out of public static hosting.

## HTTPS, Cookies, And CORS

- Serve the frontend and backend over HTTPS.
- Set `SESSION_COOKIE_SECURE=true`.
- Use `SESSION_COOKIE_SAMESITE=lax` for same-site deployments.
- Use `SESSION_COOKIE_SAMESITE=none` only when cross-site cookies are required and HTTPS is enabled.
- Set `CORS_ALLOW_LOCALHOST_REGEX=false`.
- Set `CORS_ALLOWED_ORIGINS` to the exact production frontend origin.
- Do not use wildcard CORS origins with credentialed browser sessions.

## Data Boundaries

- Back up PostgreSQL before deploying schema or data-access changes.
- Back up the Chroma persistence directory before rebuilding or replacing indexes.
- Keep `knowledge_files/`, `chroma_db/`, `logs/`, and `.env` outside public web roots.
- Deploy only `frontend/dist/` as static frontend content.
- Run the backend as a server process behind a reverse proxy or service manager.

## Logging And Audit

- Confirm backend logs are written to a private location.
- Confirm log rotation is enabled or storage limits are monitored.
- Confirm admin audit events are visible from `/admin/audit`.
- Confirm knowledge access audit events are visible from `/admin/knowledge-audit`.
- Review whether logs contain sensitive document excerpts before enabling broad operator access.

## RAG Quality Gates

- Run the maintained RAG evaluation suite before release.
- Review failure reasons for citation misses, expected source misses, and abstention failures.
- Confirm uploaded knowledge documents have department metadata where required.
- Confirm missing source files are acknowledged or cleared.
- Confirm failed index jobs are either fixed or explicitly acknowledged.

## Operational Checks

- Confirm `/health` reports `ok` before opening traffic.
- Confirm `/admin/rag/status` shows expected document, chunk, BM25, Chroma, and model usage signals.
- Confirm login, chat, streaming chat, knowledge search, upload, sync, and feedback flows work with a non-admin account and an admin account.
- Confirm daily token warning thresholds match the deployment budget.

## Rollback

- Keep the previous backend release artifact available.
- Keep the previous frontend `dist/` artifact available.
- Record the PostgreSQL backup timestamp used for rollback.
- Record the Chroma backup path used for rollback.
- If rollback restores older code, restore matching database and Chroma snapshots when schema or index behavior changed.
