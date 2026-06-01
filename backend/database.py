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
            SELECT sessions.id, sessions.expires_at, users.username
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

    return {"username": session["username"], "expires_at": session["expires_at"]}


def delete_session(session_id):
    with connect() as connection:
        connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
