import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main


class ApiAuthTests(unittest.TestCase):
    def setUp(self):
        self.api_key_patch = patch.object(main, "APP_API_KEY", "test-secret")
        self.create_client_patch = patch.object(main, "create_client", return_value=object())
        self.load_messages_patch = patch.object(main, "load_messages", return_value=[])
        self.run_agent_patch = patch.object(main, "run_agent", return_value="ok")
        self.save_messages_patch = patch.object(main, "save_messages")

        self.api_key_patch.start()
        self.create_client_patch.start()
        self.load_messages_patch.start()
        self.run_agent_patch.start()
        self.save_messages_patch.start()

    def tearDown(self):
        self.save_messages_patch.stop()
        self.run_agent_patch.stop()
        self.load_messages_patch.stop()
        self.create_client_patch.stop()
        self.api_key_patch.stop()

    def test_health_does_not_require_api_key(self):
        with TestClient(main.app) as client:
            response = client.get("/health")

        self.assertEqual(response.status_code, 200)

    def test_chat_rejects_missing_api_key(self):
        with TestClient(main.app) as client:
            response = client.post("/chat", json={"message": "hello"})

        self.assertEqual(response.status_code, 401)

    def test_chat_accepts_valid_api_key(self):
        with TestClient(main.app) as client:
            response = client.post(
                "/chat",
                json={"message": "hello"},
                headers={"X-API-Key": "test-secret"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"answer": "ok"})

    def test_files_rejects_invalid_api_key(self):
        with TestClient(main.app) as client:
            response = client.get("/files", headers={"X-API-Key": "wrong"})

        self.assertEqual(response.status_code, 401)

    def test_protected_routes_fail_when_app_api_key_is_missing(self):
        with patch.object(main, "APP_API_KEY", ""):
            with TestClient(main.app) as client:
                response = client.post(
                    "/chat",
                    json={"message": "hello"},
                    headers={"X-API-Key": "test-secret"},
                )

        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
