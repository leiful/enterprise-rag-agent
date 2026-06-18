# -*- coding: utf-8 -*-

from contextlib import contextmanager, nullcontext
import hashlib
import json
import os
import secrets
import time
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from config import APP_PASSWORD, APP_USERNAME, DATABASE_CONNECT_TIMEOUT_SECONDS, DATABASE_URL


PBKDF2_ITERATIONS = 600_000


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def _require_database_url():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is required. Configure PostgreSQL in .env.")


@contextmanager
def connect():
    _require_database_url()
    connection = psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row,
        connect_timeout=DATABASE_CONNECT_TIMEOUT_SECONDS,
    )
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def execute_script(connection, script):
    with connection.cursor() as cursor:
        cursor.execute(script)


def hash_password(password, salt=None):
    salt = salt or os.urandom(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${password_hash.hex()}"


def verify_password(password, stored_hash):
    try:
        algorithm, iterations, salt_hex, hash_hex = stored_hash.split("$")
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        int(iterations),
    ).hex()
    return secrets.compare_digest(candidate, hash_hex)


def init_db():
    with connect() as connection:
        execute_script(
            connection,
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'admin',
                departments_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at DOUBLE PRECISION NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS conversations (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                sources_json TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS vector_chunks (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                embedding_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                content_hash TEXT NOT NULL,
                token_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            ALTER TABLE vector_chunks
            ADD COLUMN IF NOT EXISTS metadata_json TEXT NOT NULL DEFAULT '{}';

            CREATE INDEX IF NOT EXISTS idx_vector_chunks_document_id
            ON vector_chunks(document_id);

            CREATE TABLE IF NOT EXISTS knowledge_documents (
                document_id TEXT PRIMARY KEY,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS departments (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS knowledge_index_jobs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                document_id TEXT,
                path TEXT,
                error TEXT,
                result_json TEXT,
                acknowledged_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS knowledge_sources (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                path TEXT NOT NULL UNIQUE,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                last_sync_at TEXT,
                last_sync_result_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS knowledge_source_files (
                id SERIAL PRIMARY KEY,
                source_id INTEGER NOT NULL REFERENCES knowledge_sources(id) ON DELETE CASCADE,
                document_id TEXT NOT NULL,
                path TEXT NOT NULL,
                content_hash TEXT,
                file_size BIGINT,
                modified_at TEXT,
                status TEXT NOT NULL,
                owns_index BOOLEAN NOT NULL DEFAULT TRUE,
                last_index_job_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (source_id, path)
            );

            CREATE TABLE IF NOT EXISTS bm25_token (
                token TEXT PRIMARY KEY,
                doc_freq INTEGER DEFAULT 0,
                total_freq INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_bm25_token_token ON bm25_token(token);

            CREATE TABLE IF NOT EXISTS bm25_posting (
                chunk_id TEXT NOT NULL REFERENCES vector_chunks(id) ON DELETE CASCADE,
                token TEXT NOT NULL,
                tf INTEGER DEFAULT 0,
                PRIMARY KEY (chunk_id, token)
            );

            CREATE INDEX IF NOT EXISTS idx_bm25_posting_token ON bm25_posting(token);
            CREATE INDEX IF NOT EXISTS idx_bm25_posting_chunk ON bm25_posting(chunk_id);

            CREATE TABLE IF NOT EXISTS bm25_stats (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                total_docs INTEGER DEFAULT 0,
                avg_doc_len DOUBLE PRECISION DEFAULT 0.0
            );

            CREATE TABLE IF NOT EXISTS knowledge_access_audit (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                username TEXT NOT NULL,
                action TEXT NOT NULL,
                query TEXT NOT NULL,
                source_count INTEGER NOT NULL DEFAULT 0,
                sources_json TEXT,
                departments_json TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS admin_audit_events (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                username TEXT NOT NULL,
                action TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT,
                details_json TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rag_feedback (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                username TEXT NOT NULL,
                conversation_id INTEGER REFERENCES conversations(id) ON DELETE SET NULL,
                message_id INTEGER REFERENCES messages(id) ON DELETE SET NULL,
                feedback_type TEXT NOT NULL,
                comment TEXT,
                query TEXT,
                answer TEXT,
                sources_json TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS model_usage_events (
                id SERIAL PRIMARY KEY,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                operation TEXT NOT NULL,
                request_id TEXT,
                usage_scope TEXT NOT NULL DEFAULT 'other',
                input_tokens_estimate INTEGER NOT NULL DEFAULT 0,
                output_tokens_estimate INTEGER NOT NULL DEFAULT 0,
                input_chars INTEGER NOT NULL DEFAULT 0,
                output_chars INTEGER NOT NULL DEFAULT 0,
                document_count INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_model_usage_events_created_at
            ON model_usage_events(created_at);

            CREATE INDEX IF NOT EXISTS idx_model_usage_events_model_operation
            ON model_usage_events(model, operation);

            """,
        )
        connection.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'admin'")
        connection.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS departments_json TEXT NOT NULL DEFAULT '[]'")
        connection.execute("ALTER TABLE knowledge_source_files ADD COLUMN IF NOT EXISTS owns_index BOOLEAN NOT NULL DEFAULT TRUE")
        connection.execute("ALTER TABLE knowledge_index_jobs ADD COLUMN IF NOT EXISTS acknowledged_at TEXT")
        connection.execute("ALTER TABLE model_usage_events ADD COLUMN IF NOT EXISTS usage_scope TEXT NOT NULL DEFAULT 'other'")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_model_usage_events_usage_scope ON model_usage_events(usage_scope)"
        )

    create_default_user()


def create_default_user():
    if not APP_USERNAME or not APP_PASSWORD:
        return

    with connect() as connection:
        existing_user = connection.execute(
            "SELECT id FROM users WHERE username = %s",
            (APP_USERNAME,),
        ).fetchone()
        if existing_user:
            return

        connection.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (%s, %s, %s, %s)",
            (APP_USERNAME, hash_password(APP_PASSWORD), "admin", utc_now_iso()),
        )


def normalize_user_role(role):
    return role if role in {"admin", "user"} else "user"


def normalize_departments(departments=None):
    if departments is None:
        return []
    if isinstance(departments, str):
        departments = [item.strip() for item in departments.split(",")]
    if not isinstance(departments, list):
        return []
    normalized = []
    seen = set()
    for department in departments:
        value = " ".join(str(department or "").split())
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(value)
    return normalized


def parse_departments_json(value):
    try:
        parsed = json.loads(value or "[]")
    except Exception:
        return []
    return normalize_departments(parsed)


def format_user_row(row):
    user = dict(row)
    user.pop("password_hash", None)
    user["role"] = normalize_user_role(user.get("role"))
    user["departments"] = parse_departments_json(user.pop("departments_json", "[]"))
    return user


def format_department_row(row):
    return dict(row)


def list_departments():
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, name, created_at
            FROM departments
            ORDER BY lower(name) ASC
            """
        ).fetchall()
    return [format_department_row(row) for row in rows]


def department_names():
    return [department["name"] for department in list_departments()]


def create_department(name):
    normalized = " ".join(str(name or "").split())
    if not normalized:
        raise ValueError("Department name is required.")

    with connect() as connection:
        row = connection.execute(
            """
            INSERT INTO departments (name, created_at)
            VALUES (%s, %s)
            RETURNING id, name, created_at
            """,
            (normalized, utc_now_iso()),
        ).fetchone()
    return format_department_row(row)


def delete_department(department_id):
    with connect() as connection:
        row = connection.execute(
            "DELETE FROM departments WHERE id = %s RETURNING id",
            (department_id,),
        ).fetchone()
    return row is not None


def list_users():
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, username, role, departments_json, created_at
            FROM users
            ORDER BY id ASC
            """
        ).fetchall()
    return [format_user_row(row) for row in rows]


def create_user(username, password, role="user", departments=None):
    username = " ".join((username or "").split())
    if not username:
        raise ValueError("Username is required.")
    if not password:
        raise ValueError("Password is required.")

    role = normalize_user_role(role)
    normalized_departments = normalize_departments(departments)
    with connect() as connection:
        row = connection.execute(
            """
            INSERT INTO users (username, password_hash, role, departments_json, created_at)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, username, role, departments_json, created_at
            """,
            (username, hash_password(password), role, json.dumps(normalized_departments, ensure_ascii=False), utc_now_iso()),
        ).fetchone()
    return format_user_row(row)


def update_user(user_id, role=None, departments=None):
    role = normalize_user_role(role)
    normalized_departments = normalize_departments(departments)
    with connect() as connection:
        row = connection.execute(
            """
            UPDATE users
            SET role = %s, departments_json = %s
            WHERE id = %s
            RETURNING id, username, role, departments_json, created_at
            """,
            (role, json.dumps(normalized_departments, ensure_ascii=False), user_id),
        ).fetchone()
    return format_user_row(row) if row else None


def authenticate_user(username, password):
    with connect() as connection:
        user = connection.execute(
            "SELECT id, username, password_hash, role, departments_json FROM users WHERE username = %s",
            (username,),
        ).fetchone()

    if not user or not verify_password(password, user["password_hash"]):
        return None

    return format_user_row(user)


def create_session(session_id, user_id, expires_at):
    with connect() as connection:
        connection.execute(
            "INSERT INTO sessions (id, user_id, expires_at, created_at) VALUES (%s, %s, %s, %s)",
            (session_id, user_id, expires_at, utc_now_iso()),
        )


def get_session(session_id, now):
    with connect() as connection:
        session = connection.execute(
            """
            SELECT sessions.id, sessions.expires_at, users.id AS user_id, users.username, users.role, users.departments_json
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.id = %s
            """,
            (session_id,),
        ).fetchone()

    if not session:
        return None

    if session["expires_at"] <= now:
        delete_session(session_id)
        return None

    return {
        "user_id": session["user_id"],
        "username": session["username"],
        "role": normalize_user_role(dict(session).get("role")),
        "departments": parse_departments_json(dict(session).get("departments_json")),
        "expires_at": session["expires_at"],
    }


def delete_session(session_id):
    with connect() as connection:
        connection.execute("DELETE FROM sessions WHERE id = %s", (session_id,))


def count_active_sessions():
    with connect() as connection:
        row = connection.execute(
            "SELECT COUNT(DISTINCT user_id) AS cnt FROM sessions WHERE expires_at > %s",
            (time.time(),),
        ).fetchone()
    return row["cnt"] if row else 0


def create_conversation(user_id, title):
    now = utc_now_iso()
    with connect() as connection:
        row = connection.execute(
            """
            INSERT INTO conversations (user_id, title, created_at, updated_at)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (user_id, title, now, now),
        ).fetchone()
        return row["id"]


def list_conversations(user_id):
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM conversations
            WHERE user_id = %s
            ORDER BY updated_at DESC, id DESC
            """,
            (user_id,),
        ).fetchall()

    return [dict(row) for row in rows]


def get_conversation(user_id, conversation_id):
    with connect() as connection:
        row = connection.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM conversations
            WHERE id = %s AND user_id = %s
            """,
            (conversation_id, user_id),
        ).fetchone()

    return dict(row) if row else None


def update_conversation_title(user_id, conversation_id, title):
    now = utc_now_iso()
    with connect() as connection:
        connection.execute(
            """
            UPDATE conversations
            SET title = %s, updated_at = %s
            WHERE id = %s AND user_id = %s
            """,
            (title, now, conversation_id, user_id),
        )


def touch_conversation(user_id, conversation_id):
    with connect() as connection:
        connection.execute(
            """
            UPDATE conversations
            SET updated_at = %s
            WHERE id = %s AND user_id = %s
            """,
            (utc_now_iso(), conversation_id, user_id),
        )


def add_message(conversation_id, role, content, sources=None):
    sources_json = json.dumps(sources or [], ensure_ascii=False) if sources is not None else None
    with connect() as connection:
        row = connection.execute(
            """
            INSERT INTO messages (conversation_id, role, content, sources_json, created_at)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (conversation_id, role, content, sources_json, utc_now_iso()),
        ).fetchone()
        return row["id"]


def save_chat_turn(user_id, conversation_id, user_message, assistant_message, sources=None, title=None):
    now = utc_now_iso()
    sources_json = json.dumps(sources or [], ensure_ascii=False) if sources is not None else None
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO messages (conversation_id, role, content, sources_json, created_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (conversation_id, "user", user_message, None, now),
        )
        connection.execute(
            """
            INSERT INTO messages (conversation_id, role, content, sources_json, created_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (conversation_id, "assistant", assistant_message, sources_json, now),
        )
        connection.execute(
            """
            UPDATE conversations
            SET updated_at = %s
            WHERE id = %s AND user_id = %s
            """,
            (now, conversation_id, user_id),
        )
        if title is not None:
            connection.execute(
                """
                UPDATE conversations
                SET title = %s, updated_at = %s
                WHERE id = %s AND user_id = %s
                """,
                (title, now, conversation_id, user_id),
            )


def build_knowledge_audit_payload(user, sources=None, access_stats=None):
    return {
        "scope": {
            "role": user.get("role"),
            "departments": user.get("departments") or [],
            "is_admin": user.get("role") == "admin",
        },
        "access_stats": access_stats or {},
        "sources": sources or [],
    }


def add_knowledge_access_audit(user, action, query, sources=None, access_stats=None):
    sources = sources or []
    departments = []
    seen_departments = set()
    for source in sources:
        metadata = source.get("metadata") if isinstance(source, dict) else {}
        department = (metadata or {}).get("department")
        if not department:
            department = source.get("department") if isinstance(source, dict) else None
        if not department:
            continue
        key = str(department).lower()
        if key in seen_departments:
            continue
        seen_departments.add(key)
        departments.append(department)
    audit_payload = build_knowledge_audit_payload(user, sources, access_stats)

    with connect() as connection:
        connection.execute(
            """
            INSERT INTO knowledge_access_audit (
                user_id,
                username,
                action,
                query,
                source_count,
                sources_json,
                departments_json,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user.get("id"),
                user.get("username") or "unknown",
                action,
                query,
                len(sources),
                json.dumps(audit_payload, ensure_ascii=False),
                json.dumps(departments, ensure_ascii=False),
                utc_now_iso(),
            ),
        )


def list_knowledge_access_audit(limit=100):
    limit = max(1, min(int(limit or 100), 500))
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, user_id, username, action, query, source_count,
                   sources_json, departments_json, created_at
            FROM knowledge_access_audit
            ORDER BY id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

    audits = []
    for row in rows:
        audit = dict(row)
        sources_payload = None
        for json_field, output_field, default in (
            ("sources_json", "sources", []),
            ("departments_json", "departments", []),
        ):
            raw_value = audit.pop(json_field, None)
            try:
                parsed = json.loads(raw_value) if raw_value else default
            except Exception:
                parsed = default
            if json_field == "sources_json" and isinstance(parsed, dict):
                sources_payload = parsed
                parsed = parsed.get("sources", [])
            audit[output_field] = parsed
        if sources_payload:
            audit["scope"] = sources_payload.get("scope") or {}
            audit["access_stats"] = sources_payload.get("access_stats") or {}
        else:
            audit["scope"] = {}
            audit["access_stats"] = {}
        audits.append(audit)
    return audits


def count_knowledge_access_audit():
    with connect() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM knowledge_access_audit"
        ).fetchone()
    return int(row["count"] or 0)


def add_admin_audit_event(user, action, target_type, target_id=None, details=None):
    action = " ".join(str(action or "").split())
    target_type = " ".join(str(target_type or "").split())
    if not action:
        raise ValueError("Admin audit action is required.")
    if not target_type:
        raise ValueError("Admin audit target type is required.")

    with connect() as connection:
        row = connection.execute(
            """
            INSERT INTO admin_audit_events (
                user_id,
                username,
                action,
                target_type,
                target_id,
                details_json,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                user.get("id"),
                user.get("username") or "unknown",
                action,
                target_type,
                None if target_id is None else str(target_id),
                json.dumps(details or {}, ensure_ascii=False),
                utc_now_iso(),
            ),
        ).fetchone()
    return row["id"]


def list_admin_audit_events(limit=100):
    limit = max(1, min(int(limit or 100), 500))
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, user_id, username, action, target_type, target_id,
                   details_json, created_at
            FROM admin_audit_events
            ORDER BY id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

    events = []
    for row in rows:
        event = dict(row)
        details_json = event.pop("details_json", None)
        try:
            event["details"] = json.loads(details_json) if details_json else {}
        except Exception:
            event["details"] = {}
        events.append(event)
    return events


def count_admin_audit_events():
    with connect() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM admin_audit_events"
        ).fetchone()
    return int(row["count"] or 0)


def add_rag_feedback(
    user,
    feedback_type,
    *,
    conversation_id=None,
    message_id=None,
    comment=None,
    query=None,
    answer=None,
    sources=None,
):
    feedback_type = " ".join(str(feedback_type or "").split())
    allowed_types = {"useful", "not_useful", "wrong_source", "outdated", "missing_doc"}
    if feedback_type not in allowed_types:
        raise ValueError("Unsupported feedback type.")

    sources_json = json.dumps(sources or [], ensure_ascii=False)
    with connect() as connection:
        row = connection.execute(
            """
            INSERT INTO rag_feedback (
                user_id,
                username,
                conversation_id,
                message_id,
                feedback_type,
                comment,
                query,
                answer,
                sources_json,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                user.get("id"),
                user.get("username") or "unknown",
                conversation_id,
                message_id,
                feedback_type,
                comment,
                query,
                answer,
                sources_json,
                utc_now_iso(),
            ),
        ).fetchone()
    return row["id"]


def list_rag_feedback(limit=100):
    limit = max(1, min(int(limit or 100), 500))
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, user_id, username, conversation_id, message_id, feedback_type,
                   comment, query, answer, sources_json, created_at
            FROM rag_feedback
            ORDER BY id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

    feedback_items = []
    for row in rows:
        item = dict(row)
        sources_json = item.pop("sources_json", None)
        try:
            item["sources"] = json.loads(sources_json) if sources_json else []
        except Exception:
            item["sources"] = []
        feedback_items.append(item)
    return feedback_items


def find_feedback_message_id(user_id, conversation_id, answer=None):
    if not conversation_id:
        return None
    answer = answer or None
    with connect() as connection:
        if answer:
            row = connection.execute(
                """
                SELECT messages.id
                FROM messages
                JOIN conversations ON conversations.id = messages.conversation_id
                WHERE conversations.user_id = %s
                  AND messages.conversation_id = %s
                  AND messages.role = 'assistant'
                  AND messages.content = %s
                ORDER BY messages.id DESC
                LIMIT 1
                """,
                (user_id, conversation_id, answer),
            ).fetchone()
            if row:
                return row["id"]

        row = connection.execute(
            """
            SELECT messages.id
            FROM messages
            JOIN conversations ON conversations.id = messages.conversation_id
            WHERE conversations.user_id = %s
              AND messages.conversation_id = %s
              AND messages.role = 'assistant'
            ORDER BY messages.id DESC
            LIMIT 1
            """,
            (user_id, conversation_id),
        ).fetchone()
    return row["id"] if row else None


def summarize_rag_feedback():
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT feedback_type, COUNT(*) AS count
            FROM rag_feedback
            GROUP BY feedback_type
            """
        ).fetchall()
    by_type = {row["feedback_type"]: int(row["count"] or 0) for row in rows}
    negative_types = {"not_useful", "wrong_source", "outdated", "missing_doc"}
    return {
        "total": sum(by_type.values()),
        "positive": by_type.get("useful", 0),
        "negative": sum(by_type.get(feedback_type, 0) for feedback_type in negative_types),
        "by_type": by_type,
    }


def get_index_job_status_counts():
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM knowledge_index_jobs
            GROUP BY status
            ORDER BY status ASC
            """
        ).fetchall()
    return {row["status"]: int(row["count"] or 0) for row in rows}


def get_unacknowledged_failed_index_job_count():
    with connect() as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM knowledge_index_jobs
            WHERE status = 'failed' AND acknowledged_at IS NULL
            """
        ).fetchone()
    return int(row["count"] or 0)


def list_failed_index_jobs(limit=20, include_acknowledged=True):
    filters = ["status = 'failed'"]
    if not include_acknowledged:
        filters.append("acknowledged_at IS NULL")

    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT id, status, document_id, path, error, created_at, updated_at, acknowledged_at
            FROM knowledge_index_jobs
            WHERE {' AND '.join(filters)}
            ORDER BY updated_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def acknowledge_failed_index_jobs(job_ids=None):
    now = utc_now_iso()
    with connect() as connection:
        if job_ids:
            rows = connection.execute(
                f"""
                UPDATE knowledge_index_jobs
                SET acknowledged_at = %s, updated_at = %s
                WHERE status = 'failed'
                  AND acknowledged_at IS NULL
                  AND id IN ({placeholders(job_ids)})
                RETURNING id
                """,
                [now, now, *job_ids],
            ).fetchall()
        else:
            rows = connection.execute(
                """
                UPDATE knowledge_index_jobs
                SET acknowledged_at = %s, updated_at = %s
                WHERE status = 'failed' AND acknowledged_at IS NULL
                RETURNING id
                """,
                (now, now),
            ).fetchall()
    return [row["id"] for row in rows]


def get_knowledge_source_file_status_counts():
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM knowledge_source_files
            GROUP BY status
            ORDER BY status ASC
            """
        ).fetchall()
    return {row["status"]: int(row["count"] or 0) for row in rows}


def list_messages(user_id, conversation_id):
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT messages.id, messages.role, messages.content, messages.sources_json, messages.created_at,
                   feedback.feedback_type AS feedback_type
            FROM messages
            JOIN conversations ON conversations.id = messages.conversation_id
            LEFT JOIN LATERAL (
                SELECT feedback_type
                FROM rag_feedback
                WHERE rag_feedback.message_id = messages.id
                  AND rag_feedback.user_id = %s
                ORDER BY rag_feedback.id DESC
                LIMIT 1
            ) feedback ON TRUE
            WHERE messages.conversation_id = %s AND conversations.user_id = %s
            ORDER BY messages.id ASC
            """,
            (user_id, conversation_id, user_id),
        ).fetchall()

    messages = []
    for row in rows:
        message = dict(row)
        feedback_type = message.pop("feedback_type", None)
        if feedback_type:
            message["feedbackSent"] = feedback_type
        sources_json = message.pop("sources_json", None)
        if sources_json:
            try:
                message["sources"] = json.loads(sources_json)
            except json.JSONDecodeError:
                message["sources"] = []
        else:
            message["sources"] = []
        messages.append(message)

    return messages


def get_bm25_stats():
    with connect() as connection:
        row = connection.execute("SELECT total_docs, avg_doc_len FROM bm25_stats WHERE id = 1").fetchone()
        if row:
            return {"total_docs": row["total_docs"], "avg_doc_len": row["avg_doc_len"]}
        return {"total_docs": 0, "avg_doc_len": 0.0}


def update_bm25_stats():
    with connect() as connection:
        result = connection.execute("SELECT COUNT(*) as cnt, AVG(token_count) as avg_len FROM vector_chunks").fetchone()
        total_docs = result["cnt"] or 0
        avg_doc_len = result["avg_len"] or 0.0

        connection.execute(
            """
            INSERT INTO bm25_stats (id, total_docs, avg_doc_len)
            VALUES (1, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                total_docs = EXCLUDED.total_docs,
                avg_doc_len = EXCLUDED.avg_doc_len
            """,
            (total_docs, avg_doc_len),
        )


def delete_bm25_for_chunk(chunk_id, connection=None):
    owns_connection = connection is None
    connection_manager = connect() if owns_connection else nullcontext(connection)
    with connection_manager as connection:
        tokens = connection.execute(
            "SELECT token, tf FROM bm25_posting WHERE chunk_id = %s",
            (chunk_id,),
        ).fetchall()

        for row in tokens:
            connection.execute(
                """
                UPDATE bm25_token
                SET doc_freq = doc_freq - 1, total_freq = total_freq - %s
                WHERE token = %s
                """,
                (row["tf"], row["token"]),
            )

        connection.execute("DELETE FROM bm25_posting WHERE chunk_id = %s", (chunk_id,))
        connection.execute("DELETE FROM bm25_token WHERE doc_freq <= 0")


def add_bm25_for_chunk(chunk_id, tokens, connection=None):
    from collections import Counter

    token_counts = Counter(tokens)
    owns_connection = connection is None
    connection_manager = connect() if owns_connection else nullcontext(connection)
    with connection_manager as connection:
        for token, tf in token_counts.items():
            connection.execute(
                """
                INSERT INTO bm25_token (token, doc_freq, total_freq)
                VALUES (%s, 1, %s)
                ON CONFLICT (token) DO UPDATE SET
                    doc_freq = bm25_token.doc_freq + 1,
                    total_freq = bm25_token.total_freq + EXCLUDED.total_freq
                """,
                (token, tf),
            )

            connection.execute(
                """
                INSERT INTO bm25_posting (chunk_id, token, tf)
                VALUES (%s, %s, %s)
                ON CONFLICT (chunk_id, token) DO UPDATE SET
                    tf = EXCLUDED.tf
                """,
                (chunk_id, token, tf),
            )


def placeholders(values):
    return ", ".join(["%s"] * len(values))


def search_bm25_postings(query_tokens):
    if not query_tokens:
        return []

    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT p.chunk_id, p.token, p.tf, t.doc_freq
            FROM bm25_posting p
            JOIN bm25_token t ON p.token = t.token
            WHERE p.token IN ({placeholders(query_tokens)})
            """,
            query_tokens,
        ).fetchall()

        postings_by_chunk = {}
        for row in rows:
            chunk_id = row["chunk_id"]
            if chunk_id not in postings_by_chunk:
                postings_by_chunk[chunk_id] = []
            postings_by_chunk[chunk_id].append({
                "token": row["token"],
                "tf": row["tf"],
                "doc_freq": row["doc_freq"],
            })

        return postings_by_chunk


def get_chunk_token_counts(chunk_ids):
    if not chunk_ids:
        return {}

    with connect() as connection:
        rows = connection.execute(
            f"SELECT id, token_count FROM vector_chunks WHERE id IN ({placeholders(chunk_ids)})",
            chunk_ids,
        ).fetchall()

        return {row["id"]: row["token_count"] for row in rows}


def ensure_model_usage_schema():
    with connect() as connection:
        execute_script(
            connection,
            """
            CREATE TABLE IF NOT EXISTS model_usage_events (
                id SERIAL PRIMARY KEY,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                operation TEXT NOT NULL,
                request_id TEXT,
                usage_scope TEXT NOT NULL DEFAULT 'other',
                input_tokens_estimate INTEGER NOT NULL DEFAULT 0,
                output_tokens_estimate INTEGER NOT NULL DEFAULT 0,
                input_chars INTEGER NOT NULL DEFAULT 0,
                output_chars INTEGER NOT NULL DEFAULT 0,
                document_count INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            """,
        )
        connection.execute("ALTER TABLE model_usage_events ADD COLUMN IF NOT EXISTS usage_scope TEXT NOT NULL DEFAULT 'other'")
        connection.execute("ALTER TABLE model_usage_events ADD COLUMN IF NOT EXISTS metadata_json TEXT NOT NULL DEFAULT '{}'")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_model_usage_events_created_at ON model_usage_events(created_at)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_model_usage_events_model_operation ON model_usage_events(model, operation)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_model_usage_events_usage_scope ON model_usage_events(usage_scope)"
        )


def add_model_usage_event(
    *,
    provider,
    model,
    operation,
    request_id=None,
    input_tokens_estimate=0,
    output_tokens_estimate=0,
    input_chars=0,
    output_chars=0,
    document_count=0,
    metadata=None,
):
    ensure_model_usage_schema()
    metadata = metadata or {}
    usage_scope = normalize_model_usage_scope(metadata.get("scope"), operation)
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO model_usage_events (
                provider, model, operation, request_id, usage_scope,
                input_tokens_estimate, output_tokens_estimate,
                input_chars, output_chars, document_count,
                metadata_json, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                provider,
                model,
                operation,
                request_id,
                usage_scope,
                int(input_tokens_estimate or 0),
                int(output_tokens_estimate or 0),
                int(input_chars or 0),
                int(output_chars or 0),
                int(document_count or 0),
                json.dumps(metadata, ensure_ascii=False),
                utc_now_iso(),
            ),
        )


def normalize_model_usage_scope(scope=None, operation=None):
    value = str(scope or "").strip()
    if value and value != "other":
        return value

    operation_value = str(operation or "").strip()
    if operation_value in {"chat", "chat_stream"}:
        return "chat"
    if operation_value == "rerank":
        return "knowledge_search"
    if operation_value == "embedding":
        return "indexing"
    return "other"


def backfill_model_usage_scopes():
    ensure_model_usage_schema()
    with connect() as connection:
        connection.execute(
            """
            UPDATE model_usage_events
            SET usage_scope = CASE
                WHEN operation IN ('chat', 'chat_stream') THEN 'chat'
                WHEN operation = 'rerank' THEN 'knowledge_search'
                WHEN operation = 'embedding' THEN 'indexing'
                ELSE usage_scope
            END
            WHERE usage_scope = 'other'
              AND operation IN ('chat', 'chat_stream', 'rerank', 'embedding')
            """
        )


def summarize_model_usage(days=1, limit=20):
    try:
        ensure_model_usage_schema()
        backfill_model_usage_scopes()
        trend_bucket = "hour" if int(days) <= 1 else "day"
        usage_filter = """
                created_at::timestamptz >= NOW() - (%s || ' days')::interval
                AND model <> 'test-model'
                """
        with connect() as connection:
            totals = connection.execute(
                f"""
                SELECT
                    COUNT(*) AS request_count,
                    COALESCE(SUM(input_tokens_estimate), 0) AS input_tokens_estimate,
                    COALESCE(SUM(output_tokens_estimate), 0) AS output_tokens_estimate,
                    COALESCE(SUM(input_chars), 0) AS input_chars,
                    COALESCE(SUM(output_chars), 0) AS output_chars,
                    COALESCE(SUM(document_count), 0) AS document_count
                FROM model_usage_events
                WHERE {usage_filter}
                """,
                (int(days),),
            ).fetchone()

            by_model = connection.execute(
                f"""
                SELECT
                    provider, model, operation, usage_scope,
                    COUNT(*) AS request_count,
                    COALESCE(SUM(input_tokens_estimate), 0) AS input_tokens_estimate,
                    COALESCE(SUM(output_tokens_estimate), 0) AS output_tokens_estimate,
                    COALESCE(SUM(input_chars), 0) AS input_chars,
                    COALESCE(SUM(output_chars), 0) AS output_chars,
                    COALESCE(SUM(document_count), 0) AS document_count
                FROM model_usage_events
                WHERE {usage_filter}
                GROUP BY provider, model, operation, usage_scope
                ORDER BY
                    COALESCE(SUM(input_tokens_estimate), 0) + COALESCE(SUM(output_tokens_estimate), 0) DESC,
                    COUNT(*) DESC
                LIMIT %s
                """,
                (int(days), int(limit)),
            ).fetchall()

            by_scope = connection.execute(
                f"""
                SELECT
                    usage_scope,
                    COUNT(*) AS request_count,
                    COALESCE(SUM(input_tokens_estimate), 0) AS input_tokens_estimate,
                    COALESCE(SUM(output_tokens_estimate), 0) AS output_tokens_estimate,
                    COALESCE(SUM(input_chars), 0) AS input_chars,
                    COALESCE(SUM(output_chars), 0) AS output_chars,
                    COALESCE(SUM(document_count), 0) AS document_count
                FROM model_usage_events
                WHERE {usage_filter}
                GROUP BY usage_scope
                ORDER BY
                    COALESCE(SUM(input_tokens_estimate), 0) + COALESCE(SUM(output_tokens_estimate), 0) DESC,
                    COUNT(*) DESC
                """,
                (int(days),),
            ).fetchall()

            trend = connection.execute(
                f"""
                SELECT
                    to_char(
                        date_trunc(%s, created_at::timestamptz AT TIME ZONE 'Asia/Shanghai'),
                        CASE WHEN %s = 'hour' THEN 'YYYY-MM-DD"T"HH24:00:00' ELSE 'YYYY-MM-DD' END
                    ) AS bucket,
                    provider,
                    model,
                    operation,
                    usage_scope,
                    COUNT(*) AS request_count,
                    COALESCE(SUM(input_tokens_estimate), 0) AS input_tokens_estimate,
                    COALESCE(SUM(output_tokens_estimate), 0) AS output_tokens_estimate,
                    COALESCE(SUM(document_count), 0) AS document_count
                FROM model_usage_events
                WHERE {usage_filter}
                GROUP BY bucket, provider, model, operation, usage_scope
                ORDER BY bucket ASC, model ASC, operation ASC, usage_scope ASC
                """,
                (trend_bucket, trend_bucket, int(days)),
            ).fetchall()

            recent_events = connection.execute(
                f"""
                SELECT
                    id, provider, model, operation, request_id, usage_scope,
                    input_tokens_estimate, output_tokens_estimate,
                    input_chars, output_chars, document_count,
                    metadata_json, created_at
                FROM model_usage_events
                WHERE {usage_filter}
                ORDER BY created_at::timestamptz DESC, id DESC
                LIMIT %s
                """,
                (int(days), int(limit)),
            ).fetchall()
    except Exception:
        totals = {}
        by_model = []
        by_scope = []
        trend = []
        recent_events = []

    return {
        "days": int(days),
        "trend_bucket": "hour" if int(days) <= 1 else "day",
        "totals": dict(totals or {}),
        "by_model": [dict(row) for row in by_model],
        "by_scope": [dict(row) for row in by_scope],
        "trend": [dict(row) for row in trend],
        "recent_events": [dict(row) for row in recent_events],
    }


def create_index_job(job_id, document_id=None, path=None, status="queued"):
    now = utc_now_iso()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO knowledge_index_jobs (
                id, status, document_id, path, error, result_json, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, NULL, NULL, %s, %s)
            """,
            (job_id, status, document_id, path, now, now),
        )


def update_index_job(
    job_id,
    *,
    status=None,
    document_id=None,
    path=None,
    error=None,
    result=None,
):
    fields = []
    values = []

    if status is not None:
        fields.append("status = %s")
        values.append(status)
    if document_id is not None:
        fields.append("document_id = %s")
        values.append(document_id)
    if path is not None:
        fields.append("path = %s")
        values.append(path)
    if error is not None:
        fields.append("error = %s")
        values.append(error)
    if result is not None:
        fields.append("result_json = %s")
        values.append(json.dumps(result, ensure_ascii=False))

    fields.append("updated_at = %s")
    values.append(utc_now_iso())
    values.append(job_id)

    with connect() as connection:
        connection.execute(
            f"UPDATE knowledge_index_jobs SET {', '.join(fields)} WHERE id = %s",
            values,
        )


def get_index_job(job_id):
    with connect() as connection:
        row = connection.execute(
            """
            SELECT id, status, document_id, path, error, result_json, acknowledged_at, created_at, updated_at
            FROM knowledge_index_jobs
            WHERE id = %s
            """,
            (job_id,),
        ).fetchone()

    if not row:
        return None

    job = dict(row)
    result_json = job.pop("result_json", None)
    if result_json:
        try:
            job["result"] = json.loads(result_json)
        except json.JSONDecodeError:
            job["result"] = None
    else:
        job["result"] = None

    return job


def upsert_knowledge_source(name, source_type, path, enabled=True):
    now = utc_now_iso()
    with connect() as connection:
        row = connection.execute(
            """
            INSERT INTO knowledge_sources (name, type, path, enabled, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (path) DO UPDATE SET
                name = EXCLUDED.name,
                type = EXCLUDED.type,
                enabled = EXCLUDED.enabled,
                updated_at = EXCLUDED.updated_at
            RETURNING id, name, type, path, enabled, last_sync_at, last_sync_result_json, created_at, updated_at
            """,
            (name, source_type, path, enabled, now, now),
        ).fetchone()
    return dict(row)


def list_knowledge_sources():
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, name, type, path, enabled, last_sync_at, last_sync_result_json, created_at, updated_at
            FROM knowledge_sources
            ORDER BY id ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_knowledge_source(source_id):
    with connect() as connection:
        row = connection.execute(
            """
            SELECT id, name, type, path, enabled, last_sync_at, last_sync_result_json, created_at, updated_at
            FROM knowledge_sources
            WHERE id = %s
            """,
            (source_id,),
        ).fetchone()
    return dict(row) if row else None


def update_knowledge_source_sync(source_id, result):
    now = utc_now_iso()
    with connect() as connection:
        connection.execute(
            """
            UPDATE knowledge_sources
            SET last_sync_at = %s, last_sync_result_json = %s, updated_at = %s
            WHERE id = %s
            """,
            (now, json.dumps(result, ensure_ascii=False), now, source_id),
        )


def upsert_knowledge_source_file(
    source_id,
    *,
    document_id,
    path,
    content_hash,
    file_size,
    modified_at,
    status,
    last_index_job_id=None,
    owns_index=True,
):
    now = utc_now_iso()
    with connect() as connection:
        row = connection.execute(
            """
            INSERT INTO knowledge_source_files (
                source_id, document_id, path, content_hash, file_size, modified_at,
                status, owns_index, last_index_job_id, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_id, path) DO UPDATE SET
                document_id = EXCLUDED.document_id,
                content_hash = EXCLUDED.content_hash,
                file_size = EXCLUDED.file_size,
                modified_at = EXCLUDED.modified_at,
                status = EXCLUDED.status,
                owns_index = EXCLUDED.owns_index,
                last_index_job_id = COALESCE(EXCLUDED.last_index_job_id, knowledge_source_files.last_index_job_id),
                updated_at = EXCLUDED.updated_at
            RETURNING id
            """,
            (
                source_id,
                document_id,
                path,
                content_hash,
                file_size,
                modified_at,
                status,
                owns_index,
                last_index_job_id,
                now,
                now,
            ),
        ).fetchone()
    return row["id"]


def list_knowledge_source_files(source_id):
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, source_id, document_id, path, content_hash, file_size, modified_at,
                   status, owns_index, last_index_job_id, created_at, updated_at
            FROM knowledge_source_files
            WHERE source_id = %s
            ORDER BY path ASC
            """,
            (source_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def delete_missing_knowledge_source_files(source_id=None):
    conditions = ["status = %s"]
    values = ["missing"]
    if source_id is not None:
        conditions.append("source_id = %s")
        values.append(source_id)

    with connect() as connection:
        rows = connection.execute(
            f"""
            DELETE FROM knowledge_source_files
            WHERE {' AND '.join(conditions)}
            RETURNING id
            """,
            values,
        ).fetchall()
    return len(rows)


def reassign_knowledge_source_files(from_document_id, to_document_id, owns_index=False):
    now = utc_now_iso()
    with connect() as connection:
        rows = connection.execute(
            """
            UPDATE knowledge_source_files
            SET document_id = %s, owns_index = %s, updated_at = %s
            WHERE document_id = %s
            RETURNING id
            """,
            (to_document_id, owns_index, now, from_document_id),
        ).fetchall()
    return len(rows)


def update_knowledge_source_file_by_job(job_id, status):
    now = utc_now_iso()
    with connect() as connection:
        connection.execute(
            """
            UPDATE knowledge_source_files
            SET status = %s, updated_at = %s
            WHERE last_index_job_id = %s
            """,
            (status, now, job_id),
        )
