import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import database
import main


class ApiAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_file = str(Path(self.temp_dir.name) / "test-agent.db")
        self.database_patch = patch.object(database, "DATABASE_FILE", self.database_file)
        self.username_patch = patch.object(main, "APP_USERNAME", "admin")
        self.password_patch = patch.object(main, "APP_PASSWORD", "password")
        self.db_username_patch = patch.object(database, "APP_USERNAME", "admin")
        self.db_password_patch = patch.object(database, "APP_PASSWORD", "password")
        self.create_client_patch = patch.object(main, "create_client", return_value=object())
        self.load_messages_patch = patch.object(main, "load_messages", return_value=[])
        self.run_agent_patch = patch.object(main, "run_agent", return_value="ok")
        self.save_messages_patch = patch.object(main, "save_messages")

        self.database_patch.start()
        self.username_patch.start()
        self.password_patch.start()
        self.db_username_patch.start()
        self.db_password_patch.start()
        self.create_client_patch.start()
        self.load_messages_patch.start()
        self.run_agent_patch.start()
        self.save_messages_patch.start()
        database.init_db()

    def tearDown(self):
        self.save_messages_patch.stop()
        self.run_agent_patch.stop()
        self.load_messages_patch.stop()
        self.create_client_patch.stop()
        self.db_password_patch.stop()
        self.db_username_patch.stop()
        self.password_patch.stop()
        self.username_patch.stop()
        self.database_patch.stop()
        self.temp_dir.cleanup()

    def session_exists(self, session_id):
        with database.connect() as connection:
            row = connection.execute(
                "SELECT id FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        return row is not None

    def default_user_id(self):
        user = database.authenticate_user("admin", "password")
        self.assertIsNotNone(user)
        return user["id"]

    def test_health_does_not_require_login(self):
        with TestClient(main.app) as client:
            response = client.get("/health")

        self.assertEqual(response.status_code, 200)

    def test_me_reports_signed_out_without_session(self):
        with TestClient(main.app) as client:
            response = client.get("/me")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"authenticated": False, "username": None})

    def test_login_rejects_invalid_password(self):
        with TestClient(main.app) as client:
            response = client.post(
                "/login",
                json={"username": "admin", "password": "wrong"},
            )

        self.assertEqual(response.status_code, 401)

    def test_login_accepts_valid_credentials(self):
        with TestClient(main.app) as client:
            response = client.post(
                "/login",
                json={"username": "admin", "password": "password"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"authenticated": True, "username": "admin"})
        self.assertIn(main.SESSION_COOKIE, response.cookies)
        self.assertIn("Max-Age=604800", response.headers["set-cookie"])
        self.assertTrue(self.session_exists(response.cookies[main.SESSION_COOKIE]))

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
        self.assertEqual(response.json(), {"answer": "ok"})

    def test_files_rejects_missing_session(self):
        with TestClient(main.app) as client:
            response = client.get("/files")

        self.assertEqual(response.status_code, 401)

    def test_logout_clears_session(self):
        with TestClient(main.app) as client:
            login_response = client.post("/login", json={"username": "admin", "password": "password"})
            session_id = login_response.cookies[main.SESSION_COOKIE]
            logout_response = client.post("/logout")
            chat_response = client.post("/chat", json={"message": "hello"})

        self.assertEqual(logout_response.status_code, 200)
        self.assertEqual(logout_response.json(), {"authenticated": False, "username": None})
        self.assertEqual(chat_response.status_code, 401)
        self.assertFalse(self.session_exists(session_id))

    def test_protected_routes_fail_when_login_config_is_missing(self):
        with patch.object(main, "APP_PASSWORD", ""):
            with TestClient(main.app) as client:
                response = client.post(
                    "/chat",
                    json={"message": "hello"},
                    cookies={main.SESSION_COOKIE: main.create_session(self.default_user_id())},
                )

        self.assertEqual(response.status_code, 503)

    def test_expired_session_is_rejected_and_removed(self):
        with patch.object(main, "time") as fake_time:
            fake_time.time.return_value = 100
            session_id = main.create_session(self.default_user_id())
            fake_time.time.return_value = 100 + main.SESSION_MAX_AGE_SECONDS + 1

            with TestClient(main.app) as client:
                response = client.post(
                    "/chat",
                    json={"message": "hello"},
                    cookies={main.SESSION_COOKIE: session_id},
                )

        self.assertEqual(response.status_code, 401)
        self.assertFalse(self.session_exists(session_id))


if __name__ == "__main__":
    unittest.main()
