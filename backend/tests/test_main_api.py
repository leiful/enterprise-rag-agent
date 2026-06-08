import warnings
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

warnings.filterwarnings(
    "ignore",
    message=r"Using `httpx` with `starlette\.testclient` is deprecated; install `httpx2` instead\.",
    category=Warning,
)

from fastapi.testclient import TestClient

import database
import main
import vector_store
from tests.test_db_utils import patched_postgres_database
from tests.test_vector_store import FakeEmbeddingClient


class ApiAuthTests(unittest.TestCase):
    def setUp(self):
        self.username_patch = patch.object(main, "APP_USERNAME", "admin")
        self.password_patch = patch.object(main, "APP_PASSWORD", "password")
        self.db_username_patch = patch.object(database, "APP_USERNAME", "admin")
        self.db_password_patch = patch.object(database, "APP_PASSWORD", "password")
        self.create_client_patch = patch.object(main, "create_client", return_value=object())
        self.rerank_key_patch = patch("services.rerank_service.RERANK_API_KEY", "")
        self.run_agent_patch = patch.object(
            main,
            "run_agent",
            return_value={
                "answer": "ok",
                "sources": [
                    {
                        "label": "K1",
                        "document_id": "notes.md",
                        "chunk_id": "notes.md_chunk_0000",
                        "chunk_index": 0,
                        "score": 0.7,
                        "text": "source text",
                    }
                ],
            },
        )

        self.database_context = patched_postgres_database()
        self.temp_dir = TemporaryDirectory()
        self.database_context.__enter__()
        self.username_patch.start()
        self.password_patch.start()
        self.db_username_patch.start()
        self.db_password_patch.start()
        self.create_client_patch.start()
        self.rerank_key_patch.start()
        self.run_agent_patch.start()

    def tearDown(self):
        main.login_failures.clear()
        with main.chat_admission_lock:
            main.active_chat_total = 0
            main.active_chat_by_user.clear()
            main.active_chat_by_conversation.clear()
        vector_store.clear_runtime_caches()
        self.run_agent_patch.stop()
        self.rerank_key_patch.stop()
        self.create_client_patch.stop()
        self.db_password_patch.stop()
        self.db_username_patch.stop()
        self.password_patch.stop()
        self.username_patch.stop()
        self.database_context.__exit__(None, None, None)
        self.temp_dir.cleanup()

    def session_exists(self, session_id):
        with database.connect() as connection:
            row = connection.execute(
                "SELECT id FROM sessions WHERE id = %s",
                (session_id,),
            ).fetchone()
        return row is not None

    def default_user_id(self):
        user = database.authenticate_user("admin", "password")
        self.assertIsNotNone(user)
        return user["id"]

    def wait_for_job(self, client, job_id):
        response = client.get(f"/knowledge/index-jobs/{job_id}")
        self.assertEqual(response.status_code, 200)
        return response

    def test_health_does_not_require_login(self):
        with TestClient(main.app) as client:
            response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertIn("checks", response.json())

    def test_health_reports_config_warnings(self):
        issues = [
            {
                "name": "APP_PASSWORD",
                "severity": "warning",
                "message": "weak password",
            }
        ]

        with patch.object(main, "validate_runtime_config", return_value=issues):
            with TestClient(main.app) as client:
                response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "degraded")
        self.assertEqual(response.json()["checks"]["config"]["status"], "warning")
        self.assertEqual(response.json()["checks"]["config"]["issues"], issues)

    def test_health_reports_config_errors(self):
        issues = [
            {
                "name": "VECTOR_STORE_BACKEND",
                "severity": "error",
                "message": "invalid backend",
            }
        ]

        with patch.object(main, "validate_runtime_config", return_value=issues):
            with TestClient(main.app) as client:
                response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "error")
        self.assertEqual(response.json()["checks"]["config"]["status"], "error")

    def test_health_reports_database_errors(self):
        with patch.object(main, "get_database_health", return_value={"status": "error", "error": "db failed"}):
            with TestClient(main.app) as client:
                response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "error")
        self.assertEqual(response.json()["checks"]["database"]["status"], "error")

    def test_me_reports_signed_out_without_session(self):
        with TestClient(main.app) as client:
            response = client.get("/me")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"authenticated": False, "username": None, "role": None, "departments": []},
        )

    def test_login_rejects_invalid_password(self):
        with TestClient(main.app) as client:
            response = client.post(
                "/login",
                json={"username": "admin", "password": "wrong"},
            )

        self.assertEqual(response.status_code, 401)

    def test_login_rate_limits_repeated_failures(self):
        with patch.object(main, "LOGIN_MAX_FAILED_ATTEMPTS", 2):
            with patch.object(main, "LOGIN_LOCKOUT_SECONDS", 60):
                with TestClient(main.app) as client:
                    first_response = client.post(
                        "/login",
                        json={"username": "admin", "password": "wrong"},
                    )
                    second_response = client.post(
                        "/login",
                        json={"username": "admin", "password": "wrong"},
                    )
                    third_response = client.post(
                        "/login",
                        json={"username": "admin", "password": "wrong"},
                    )

        self.assertEqual(first_response.status_code, 401)
        self.assertEqual(second_response.status_code, 401)
        self.assertEqual(third_response.status_code, 429)
        self.assertEqual(third_response.headers["Retry-After"], "60")

    def test_login_accepts_valid_credentials(self):
        with TestClient(main.app) as client:
            response = client.post(
                "/login",
                json={"username": "admin", "password": "password"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"authenticated": True, "username": "admin", "role": "admin", "departments": []},
        )
        self.assertIn(main.SESSION_COOKIE, response.cookies)
        self.assertIn("Max-Age=604800", response.headers["set-cookie"])
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertIn("SameSite=lax", response.headers["set-cookie"])
        self.assertTrue(self.session_exists(response.cookies[main.SESSION_COOKIE]))

    def test_login_can_set_secure_cookie_for_https_deployments(self):
        with patch.object(main, "SESSION_COOKIE_SECURE", True):
            with TestClient(main.app) as client:
                response = client.post(
                    "/login",
                    json={"username": "admin", "password": "password"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Secure", response.headers["set-cookie"])

    def test_responses_include_security_headers(self):
        with TestClient(main.app) as client:
            response = client.get("/health")

        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")

    def test_login_creates_random_session_ids(self):
        with TestClient(main.app) as client:
            first_response = client.post(
                "/login",
                json={"username": "admin", "password": "password"},
            )
            second_response = client.post(
                "/login",
                json={"username": "admin", "password": "password"},
            )

        self.assertNotEqual(
            first_response.cookies[main.SESSION_COOKIE],
            second_response.cookies[main.SESSION_COOKIE],
        )

    def test_admin_can_manage_departments(self):
        with TestClient(main.app) as client:
            client.post("/login", json={"username": "admin", "password": "password"})
            create_response = client.post("/admin/departments", json={"name": "Finance"})
            list_response = client.get("/admin/departments")
            audit_response = client.get("/admin/audit")
            delete_response = client.delete(f"/admin/departments/{create_response.json()['department']['id']}")

        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(list_response.json()["departments"][0]["name"], "Finance")
        self.assertEqual(audit_response.status_code, 200)
        self.assertEqual(audit_response.json()["events"][0]["action"], "department.create")
        self.assertEqual(audit_response.json()["events"][0]["details"]["name"], "Finance")
        self.assertEqual(delete_response.status_code, 200)

    def test_create_user_rejects_unknown_department(self):
        with TestClient(main.app) as client:
            client.post("/login", json={"username": "admin", "password": "password"})
            response = client.post(
                "/admin/users",
                json={
                    "username": "analyst",
                    "password": "long-enough-password",
                    "role": "user",
                    "departments": ["Unknown"],
                },
            )

        self.assertEqual(response.status_code, 400)

    def test_admin_can_update_user_department(self):
        user = database.create_user(
            "employee",
            "strong-password-123",
            "user",
            departments=["Finance"],
        )
        database.create_department("User Edit Support")

        with TestClient(main.app) as client:
            client.post("/login", json={"username": "admin", "password": "password"})
            response = client.patch(
                f"/admin/users/{user['id']}",
                json={"role": "user", "departments": ["User Edit Support"]},
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["departments"], ["User Edit Support"])

    def test_create_user_requires_department(self):
        with TestClient(main.app) as client:
            client.post("/login", json={"username": "admin", "password": "password"})
            response = client.post(
                "/admin/users",
                json={
                    "username": "analyst",
                    "password": "long-enough-password",
                    "role": "user",
                    "departments": [],
                },
            )

        self.assertEqual(response.status_code, 400)

    def test_chat_rejects_missing_session(self):
        with TestClient(main.app) as client:
            response = client.post("/chat", json={"message": "hello"})

        self.assertEqual(response.status_code, 401)

    def test_chat_accepts_logged_in_session(self):
        with TestClient(main.app) as client:
            login_response = client.post(
                "/login",
                json={"username": "admin", "password": "password"},
            )
            response = client.post("/chat", json={"message": "hello"})

        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["answer"], "ok")
        self.assertIsInstance(data["conversation_id"], int)
        self.assertEqual(data["sources"][0]["label"], "K1")

        messages = database.list_messages(self.default_user_id(), data["conversation_id"])
        self.assertEqual(
            [(message["role"], message["content"]) for message in messages],
            [("user", "hello"), ("assistant", "ok")],
        )
        self.assertEqual(messages[-1]["sources"][0]["document_id"], "notes.md")

    def test_chat_stream_accepts_logged_in_session(self):
        preflight = {
            "content": "Knowledge base preflight result:\nsource\n\nUser question:\nhello",
            "sources": [
                {
                    "label": "K1",
                    "document_id": "stream.md",
                    "chunk_id": "stream.md_chunk_0000",
                    "chunk_index": 0,
                    "score": 0.8,
                    "text": "stream source",
                }
            ],
        }
        with patch("main.build_knowledge_preflight", return_value=preflight):
            with patch("main.run_agent_stream", return_value=iter(["hello ", "there"])):
                with TestClient(main.app) as client:
                    login_response = client.post(
                        "/login",
                        json={"username": "admin", "password": "password"},
                    )
                    response = client.post("/chat/stream", json={"message": "hello"})

        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "hello there")
        self.assertTrue(response.headers["X-Knowledge-Sources"])

        conversation_id = int(response.headers["X-Conversation-Id"])
        messages = database.list_messages(self.default_user_id(), conversation_id)
        self.assertEqual(
            [(message["role"], message["content"]) for message in messages],
            [("user", "hello"), ("assistant", "hello there")],
        )
        self.assertEqual(messages[-1]["sources"][0]["document_id"], "stream.md")

    def test_chat_rejects_when_user_already_has_running_request(self):
        with patch.object(main, "CHAT_MAX_CONCURRENT_PER_USER", 1):
            with TestClient(main.app) as client:
                client.post("/login", json={"username": "admin", "password": "password"})
                conversation_id = database.create_conversation(self.default_user_id(), "Busy")
                with main.ChatAdmission(self.default_user_id(), conversation_id):
                    response = client.post("/chat", json={"message": "hello"})

        self.assertEqual(response.status_code, 429)
        self.assertIn("already have a chat request running", response.json()["detail"])

    def test_chat_admission_is_released_after_request(self):
        with TestClient(main.app) as client:
            client.post("/login", json={"username": "admin", "password": "password"})
            response = client.post("/chat", json={"message": "hello"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(main.current_chat_admission_status()["active"], 0)

    def test_chat_appends_to_existing_conversation(self):
        user_id = self.default_user_id()
        conversation_id = database.create_conversation(user_id, "Existing")
        database.add_message(conversation_id, "user", "first")
        database.add_message(conversation_id, "assistant", "second")

        with TestClient(main.app) as client:
            client.post("/login", json={"username": "admin", "password": "password"})
            response = client.post(
                "/chat",
                json={"message": "continue", "conversation_id": conversation_id},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["conversation_id"], conversation_id)

        messages = database.list_messages(user_id, conversation_id)
        self.assertEqual(messages[-2]["content"], "continue")
        self.assertEqual(messages[-1]["content"], "ok")

    def test_conversations_list_requires_login(self):
        with TestClient(main.app) as client:
            response = client.get("/conversations")

        self.assertEqual(response.status_code, 401)

    def test_logged_in_user_can_list_conversations_and_messages(self):
        user_id = self.default_user_id()
        conversation_id = database.create_conversation(user_id, "Saved")
        database.add_message(conversation_id, "user", "hello")

        with TestClient(main.app) as client:
            client.post("/login", json={"username": "admin", "password": "password"})
            conversations_response = client.get("/conversations")
            messages_response = client.get(f"/conversations/{conversation_id}/messages")

        self.assertEqual(conversations_response.status_code, 200)
        self.assertEqual(
            conversations_response.json()["conversations"][0]["title"],
            "Saved",
        )
        self.assertEqual(messages_response.status_code, 200)
        self.assertEqual(messages_response.json()["messages"][0]["content"], "hello")

    def test_chat_rejects_unknown_conversation(self):
        with TestClient(main.app) as client:
            client.post("/login", json={"username": "admin", "password": "password"})
            response = client.post(
                "/chat",
                json={"message": "hello", "conversation_id": 999},
            )

        self.assertEqual(response.status_code, 404)

    def test_files_rejects_missing_session(self):
        with TestClient(main.app) as client:
            response = client.get("/files")

        self.assertEqual(response.status_code, 401)

    def test_deepseek_balance_requires_login(self):
        with TestClient(main.app) as client:
            response = client.get("/billing/deepseek-balance")

        self.assertEqual(response.status_code, 401)

    def test_logged_in_user_can_view_deepseek_balance(self):
        class FakeBalanceResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return (
                    b'{"is_available":true,"balance_infos":[{"currency":"USD",'
                    b'"total_balance":"12.34","granted_balance":"1.00",'
                    b'"topped_up_balance":"11.34"}]}'
                )

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}):
            with patch("main.urlopen", return_value=FakeBalanceResponse()) as urlopen_mock:
                with TestClient(main.app) as client:
                    client.post("/login", json={"username": "admin", "password": "password"})
                    response = client.get("/billing/deepseek-balance")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["is_available"], True)
        self.assertEqual(response.json()["balance_infos"][0]["currency"], "USD")
        self.assertEqual(response.json()["balance_infos"][0]["total_balance"], "12.34")
        request = urlopen_mock.call_args.args[0]
        self.assertEqual(request.headers["Authorization"], "Bearer test-key")

    def test_index_knowledge_file_requires_login(self):
        with TestClient(main.app) as client:
            response = client.post(
                "/knowledge/index-file",
                json={"path": "ENGINEERING_NOTES.md"},
            )

        self.assertEqual(response.status_code, 401)

    def test_upload_knowledge_file_requires_login(self):
        with TestClient(main.app) as client:
            response = client.post(
                "/knowledge/upload",
                files={"file": ("notes.md", b"agent tool memory", "text/markdown")},
            )

        self.assertEqual(response.status_code, 401)

    def test_logged_in_user_can_upload_and_index_knowledge_file(self):
        upload_dir = Path(self.temp_dir.name) / "knowledge_files"

        with patch("knowledge.KNOWLEDGE_FILES_DIR", upload_dir):
            with patch("knowledge.PROJECT_ROOT", Path(self.temp_dir.name)):
                with patch("vector_store.EmbeddingClient", return_value=FakeEmbeddingClient()):
                    with TestClient(main.app) as client:
                        client.post("/login", json={"username": "admin", "password": "password"})
                        upload_response = client.post(
                            "/knowledge/upload",
                            data={"notes": "deployment checklist"},
                            files={
                                "file": (
                                    "notes.md",
                                    b"agent tool memory",
                                    "text/markdown",
                                )
                            },
                        )
                        job_response = self.wait_for_job(client, upload_response.json()["job_id"])
                        documents_response = client.get("/knowledge/documents")

        self.assertEqual(upload_response.status_code, 202)
        self.assertEqual(upload_response.json()["document_id"], "notes.md")
        self.assertEqual(job_response.json()["status"], "completed")
        self.assertEqual(job_response.json()["result"]["document_id"], "notes.md")
        self.assertEqual(job_response.json()["result"]["chunk_count"], 1)
        self.assertEqual(job_response.json()["result"]["notes"], "deployment checklist")
        self.assertEqual(
            documents_response.json()["documents"][0]["document_id"],
            "notes.md",
        )
        self.assertEqual(
            documents_response.json()["documents"][0]["notes"],
            "deployment checklist",
        )
        self.assertEqual(
            (upload_dir / "notes.md").read_text(encoding="utf-8"),
            "agent tool memory",
        )

    def test_upload_knowledge_file_rejects_large_file(self):
        upload_dir = Path(self.temp_dir.name) / "knowledge_files"

        with patch("knowledge.MAX_UPLOAD_BYTES", 5):
            with patch("knowledge.KNOWLEDGE_FILES_DIR", upload_dir):
                with patch("knowledge.PROJECT_ROOT", Path(self.temp_dir.name)):
                    with TestClient(main.app) as client:
                        client.post("/login", json={"username": "admin", "password": "password"})
                        response = client.post(
                            "/knowledge/upload",
                            files={
                                "file": (
                                    "large.md",
                                    b"0123456789",
                                    "text/markdown",
                                )
                            },
                        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("larger than 50MB", response.json()["detail"])
        self.assertFalse((upload_dir / "large.md").exists())

    def test_upload_knowledge_file_rejects_reserved_windows_name(self):
        upload_dir = Path(self.temp_dir.name) / "knowledge_files"

        with patch("knowledge.KNOWLEDGE_FILES_DIR", upload_dir):
            with patch("knowledge.PROJECT_ROOT", Path(self.temp_dir.name)):
                with TestClient(main.app) as client:
                    client.post("/login", json={"username": "admin", "password": "password"})
                    response = client.post(
                        "/knowledge/upload",
                        files={"file": ("CON.txt", b"agent tool memory", "text/plain")},
                    )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "file extension is not supported")
        self.assertFalse((upload_dir / "CON.txt").exists())

    def test_logged_in_user_can_index_and_search_knowledge_file(self):
        with patch("vector_store.EmbeddingClient", return_value=FakeEmbeddingClient()):
            with TestClient(main.app) as client:
                client.post("/login", json={"username": "admin", "password": "password"})
                index_response = client.post(
                    "/knowledge/index-file",
                    json={
                        "path": "notes.md",
                        "document_id": "notes",
                    },
                )

                self.assertEqual(index_response.status_code, 400)

        notes_path = Path(self.temp_dir.name) / "notes.md"
        notes_path.write_text("agent tool memory", encoding="utf-8")

        with patch.object(main.knowledge, "PROJECT_ROOT", Path(self.temp_dir.name)):
            with patch("knowledge.PROJECT_ROOT", Path(self.temp_dir.name)):
                with patch("vector_store.EmbeddingClient", return_value=FakeEmbeddingClient()):
                    with TestClient(main.app) as client:
                        client.post("/login", json={"username": "admin", "password": "password"})
                        index_response = client.post(
                            "/knowledge/index-file",
                            json={
                                "path": "notes.md",
                                "document_id": "notes",
                                "notes": "vector database context",
                            },
                        )
                        job_response = self.wait_for_job(client, index_response.json()["job_id"])
                        documents_response = client.get("/knowledge/documents")
                        search_response = client.post(
                            "/knowledge/search",
                            json={"query": "agent tool", "top_k": 1, "min_score": 0},
                        )

        self.assertEqual(index_response.status_code, 202)
        self.assertEqual(job_response.json()["status"], "completed")
        self.assertEqual(job_response.json()["result"]["chunk_count"], 1)
        self.assertEqual(job_response.json()["result"]["notes"], "vector database context")
        self.assertEqual(
            documents_response.json()["documents"][0]["document_id"],
            "notes",
        )
        self.assertEqual(
            documents_response.json()["documents"][0]["notes"],
            "vector database context",
        )
        self.assertEqual(
            search_response.json()["results"][0]["document_id"],
            "notes",
        )

    def test_index_knowledge_file_rejects_invalid_metadata_before_queueing(self):
        notes_path = Path(self.temp_dir.name) / "notes.md"
        notes_path.write_text("agent tool memory", encoding="utf-8")

        with patch("knowledge.PROJECT_ROOT", Path(self.temp_dir.name)):
            with TestClient(main.app) as client:
                client.post("/login", json={"username": "admin", "password": "password"})
                response = client.post(
                    "/knowledge/index-file",
                    json={
                        "path": "notes.md",
                        "document_id": "notes",
                        "metadata": {"sensitivity": "secret"},
                    },
                )

        self.assertEqual(response.status_code, 400)
        self.assertIn("metadata.sensitivity must be one of", response.json()["detail"])

    def test_upload_knowledge_file_rejects_malformed_metadata_json(self):
        upload_dir = Path(self.temp_dir.name) / "knowledge_files"

        with patch("knowledge.KNOWLEDGE_FILES_DIR", upload_dir):
            with patch("knowledge.PROJECT_ROOT", Path(self.temp_dir.name)):
                with TestClient(main.app) as client:
                    client.post("/login", json={"username": "admin", "password": "password"})
                    response = client.post(
                        "/knowledge/upload",
                        data={"metadata": "{not-json"},
                        files={"file": ("notes.md", b"agent tool memory", "text/markdown")},
                    )

        self.assertEqual(response.status_code, 400)
        self.assertIn("metadata must be valid JSON", response.json()["detail"])
        self.assertFalse((upload_dir / "notes.md").exists())

    def test_logged_in_user_can_delete_knowledge_document(self):
        notes_path = Path(self.temp_dir.name) / "notes.md"
        notes_path.write_text("agent tool memory", encoding="utf-8")

        with patch("knowledge.PROJECT_ROOT", Path(self.temp_dir.name)):
            with patch("vector_store.EmbeddingClient", return_value=FakeEmbeddingClient()):
                with TestClient(main.app) as client:
                    client.post("/login", json={"username": "admin", "password": "password"})
                    index_response = client.post(
                        "/knowledge/index-file",
                        json={"path": "notes.md", "document_id": "notes"},
                    )
                    self.wait_for_job(client, index_response.json()["job_id"])
                    delete_response = client.delete("/knowledge/documents/notes")
                    documents_response = client.get("/knowledge/documents")

        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(documents_response.json()["documents"], [])

    def test_knowledge_search_filters_by_min_score(self):
        notes_path = Path(self.temp_dir.name) / "notes.md"
        notes_path.write_text("agent tool memory", encoding="utf-8")

        with patch("knowledge.PROJECT_ROOT", Path(self.temp_dir.name)):
            with patch("vector_store.EmbeddingClient", return_value=FakeEmbeddingClient()):
                with TestClient(main.app) as client:
                    client.post("/login", json={"username": "admin", "password": "password"})
                    index_response = client.post(
                        "/knowledge/index-file",
                        json={"path": "notes.md", "document_id": "notes"},
                    )
                    self.wait_for_job(client, index_response.json()["job_id"])
                    kept_response = client.post(
                        "/knowledge/search",
                        json={"query": "agent tool", "top_k": 3, "min_score": 0},
                    )
                    filtered_response = client.post(
                        "/knowledge/search",
                        json={"query": "agent tool", "top_k": 3, "min_score": 1.01},
                    )

        self.assertEqual(kept_response.status_code, 200)
        self.assertEqual(len(kept_response.json()["results"]), 1)
        self.assertEqual(filtered_response.status_code, 200)
        self.assertEqual(filtered_response.json()["results"], [])

    def test_logout_clears_session(self):
        with TestClient(main.app) as client:
            login_response = client.post("/login", json={"username": "admin", "password": "password"})
            session_id = login_response.cookies[main.SESSION_COOKIE]
            logout_response = client.post("/logout")
            chat_response = client.post("/chat", json={"message": "hello"})

        self.assertEqual(logout_response.status_code, 200)
        self.assertEqual(
            logout_response.json(),
            {"authenticated": False, "username": None, "role": None, "departments": []},
        )
        self.assertEqual(chat_response.status_code, 401)
        self.assertFalse(self.session_exists(session_id))

    def test_protected_routes_fail_when_login_config_is_missing(self):
        with patch.object(main, "APP_PASSWORD", ""):
            with TestClient(main.app) as client:
                client.cookies.set(main.SESSION_COOKIE, main.create_session(self.default_user_id()))
                response = client.post(
                    "/chat",
                    json={"message": "hello"},
                )

        self.assertEqual(response.status_code, 503)

    def test_expired_session_is_rejected_and_removed(self):
        with patch.object(main, "time") as fake_time:
            fake_time.time.return_value = 100
            session_id = main.create_session(self.default_user_id())
            fake_time.time.return_value = 100 + main.SESSION_MAX_AGE_SECONDS + 1

            with TestClient(main.app) as client:
                client.cookies.set(main.SESSION_COOKIE, session_id)
                response = client.post(
                    "/chat",
                    json={"message": "hello"},
                )

        self.assertEqual(response.status_code, 401)
        self.assertFalse(self.session_exists(session_id))


if __name__ == "__main__":
    unittest.main()
