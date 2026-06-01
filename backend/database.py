# -*- coding: utf-8 -*-

from contextlib import contextmanager
import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timezone

from config import APP_PASSWORD, APP_USERNAME, DATABASE_FILE


PBKDF2_ITERATIONS = 600_000


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect():
    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


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
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at REAL NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );
            """
        )

    create_default_user()


def create_default_user():
    if not APP_USERNAME or not APP_PASSWORD:
        return

    with connect() as connection:
        existing_user = connection.execute(
            "SELECT id FROM users WHERE username = ?",
            (APP_USERNAME,),
        ).fetchone()
        if existing_user:
            return

        connection.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (APP_USERNAME, hash_password(APP_PASSWORD), utc_now_iso()),
        )


def authenticate_user(username, password):
    with connect() as connection:
        user = connection.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?",
            (username,),
        ).fetchone()

    if not user or not verify_password(password, user["password_hash"]):
        return None

    return {"id": user["id"], "username": user["username"]}


def create_session(session_id, user_id, expires_at):
    with connect() as connection:
        connection.execute(
            "INSERT INTO sessions (id, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (session_id, user_id, expires_at, utc_now_iso()),
        )


def get_session(session_id, now):
    with connect() as connection:
        session = connection.execute(
            """
            SELECT sessions.id, sessions.expires_at, users.id AS user_id, users.username
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.id = ?
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
        "expires_at": session["expires_at"],
    }


def delete_session(session_id):
    with connect() as connection:
        connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def create_conversation(user_id, title):
    now = utc_now_iso()
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO conversations (user_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, title, now, now),
        )
        return cursor.lastrowid


def list_conversations(user_id):
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM conversations
            WHERE user_id = ?
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
            WHERE id = ? AND user_id = ?
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
            SET title = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (title, now, conversation_id, user_id),
        )


def touch_conversation(user_id, conversation_id):
    with connect() as connection:
        connection.execute(
            """
            UPDATE conversations
            SET updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (utc_now_iso(), conversation_id, user_id),
        )


def add_message(conversation_id, role, content):
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO messages (conversation_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (conversation_id, role, content, utc_now_iso()),
        )
        return cursor.lastrowid


def list_messages(user_id, conversation_id):
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT messages.id, messages.role, messages.content, messages.created_at
            FROM messages
            JOIN conversations ON conversations.id = messages.conversation_id
            WHERE messages.conversation_id = ? AND conversations.user_id = ?
            ORDER BY messages.id ASC
            """,
            (conversation_id, user_id),
        ).fetchall()

    return [dict(row) for row in rows]
