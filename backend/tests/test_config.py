import unittest
from unittest.mock import patch

import config


class ConfigValidationTests(unittest.TestCase):
    def setUp(self):
        self.model_patcher = patch.object(config, "MODEL", "test-chat-model")
        self.base_url_patcher = patch.object(config, "BASE_URL", "https://api.example.com")
        self.model_patcher.start()
        self.base_url_patcher.start()

    def tearDown(self):
        self.base_url_patcher.stop()
        self.model_patcher.stop()

    def test_validate_runtime_config_reports_invalid_vector_backend(self):
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "model-key"}):
            with patch.object(config, "APP_USERNAME", "admin"):
                with patch.object(config, "APP_PASSWORD", "strong-local-password"):
                    with patch.object(config, "DATABASE_URL", "postgresql://user:pass@localhost:5432/app"):
                        with patch.object(config, "VECTOR_STORE_BACKEND", "unknown"):
                            issues = config.validate_runtime_config()

        self.assertIn("VECTOR_STORE_BACKEND", {issue["name"] for issue in issues})
        self.assertIn("error", {issue["severity"] for issue in issues})

    def test_validate_runtime_config_warns_about_weak_password(self):
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "model-key"}):
            with patch.object(config, "APP_USERNAME", "admin"):
                with patch.object(config, "APP_PASSWORD", "123456"):
                    with patch.object(config, "DATABASE_URL", "postgresql://user:pass@localhost:5432/app"):
                        with patch.object(config, "VECTOR_STORE_BACKEND", "chroma"):
                            issues = config.validate_runtime_config()

        matching = [
            issue for issue in issues
            if issue["name"] == "APP_PASSWORD" and issue["severity"] == "warning"
        ]
        self.assertTrue(matching)

    def test_validate_runtime_config_accepts_chroma_directory_parent(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "model-key"}):
                with patch.object(config, "APP_USERNAME", "admin"):
                    with patch.object(config, "APP_PASSWORD", "strong-local-password"):
                        with patch.object(config, "DATABASE_URL", "postgresql://user:pass@localhost:5432/app"):
                            with patch.object(config, "EMBEDDING_API_KEY", "embedding-key"):
                                with patch.object(config, "VECTOR_STORE_BACKEND", "chroma"):
                                    with patch.object(config, "CHROMA_COLLECTION_NAME", "agent_knowledge"):
                                        with patch.object(config, "CHROMA_PERSIST_DIR", Path(temp_dir) / "chroma_db"):
                                            issues = config.validate_runtime_config()

        self.assertEqual(
            [issue for issue in issues if issue["severity"] == "error"],
            [],
        )

    def test_validate_runtime_config_requires_secure_cookie_for_samesite_none(self):
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "model-key"}):
            with patch.object(config, "APP_USERNAME", "admin"):
                with patch.object(config, "APP_PASSWORD", "strong-local-password"):
                    with patch.object(config, "DATABASE_URL", "postgresql://user:pass@localhost:5432/app"):
                        with patch.object(config, "VECTOR_STORE_BACKEND", "chroma"):
                            with patch.object(config, "SESSION_COOKIE_SAMESITE", "none"):
                                with patch.object(config, "SESSION_COOKIE_SECURE", False):
                                    issues = config.validate_runtime_config()

        self.assertIn("SESSION_COOKIE_SECURE", {issue["name"] for issue in issues})

    def test_cors_helpers_parse_default_local_origins(self):
        with patch.object(config, "CORS_ALLOWED_ORIGINS", "http://localhost:5173, http://127.0.0.1:5173"):
            with patch.object(config, "CORS_ALLOW_LOCALHOST_REGEX", True):
                self.assertEqual(
                    config.cors_allowed_origins(),
                    ["http://localhost:5173", "http://127.0.0.1:5173"],
                )
                self.assertIsNotNone(config.cors_allow_origin_regex())

    def test_validate_runtime_config_requires_secure_cookie_in_production(self):
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "model-key"}):
            with patch.object(config, "APP_ENV", "production"):
                with patch.object(config, "APP_USERNAME", "admin"):
                    with patch.object(config, "APP_PASSWORD", "strong-local-password"):
                        with patch.object(config, "DATABASE_URL", "postgresql://user:pass@localhost:5432/app"):
                            with patch.object(config, "VECTOR_STORE_BACKEND", "chroma"):
                                with patch.object(config, "SESSION_COOKIE_SECURE", False):
                                    issues = config.validate_runtime_config()

        matching = [
            issue for issue in issues
            if issue["name"] == "SESSION_COOKIE_SECURE" and issue["severity"] == "error"
        ]
        self.assertTrue(matching)

    def test_validate_runtime_config_warns_about_localhost_cors_in_production(self):
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "model-key"}):
            with patch.object(config, "APP_ENV", "production"):
                with patch.object(config, "APP_USERNAME", "admin"):
                    with patch.object(config, "APP_PASSWORD", "strong-local-password"):
                        with patch.object(config, "DATABASE_URL", "postgresql://user:pass@localhost:5432/app"):
                            with patch.object(config, "VECTOR_STORE_BACKEND", "chroma"):
                                with patch.object(config, "SESSION_COOKIE_SECURE", True):
                                    with patch.object(config, "CORS_ALLOWED_ORIGINS", "http://localhost:5173"):
                                        with patch.object(config, "CORS_ALLOW_LOCALHOST_REGEX", True):
                                            issues = config.validate_runtime_config()

        issue_names = {issue["name"] for issue in issues if issue["severity"] == "warning"}
        self.assertIn("CORS_ALLOWED_ORIGINS", issue_names)
        self.assertIn("CORS_ALLOW_LOCALHOST_REGEX", issue_names)

    def test_validate_runtime_config_rejects_invalid_query_coverage_threshold(self):
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "model-key"}):
            with patch.object(config, "APP_USERNAME", "admin"):
                with patch.object(config, "APP_PASSWORD", "strong-local-password"):
                    with patch.object(config, "DATABASE_URL", "postgresql://user:pass@localhost:5432/app"):
                        with patch.object(config, "VECTOR_STORE_BACKEND", "chroma"):
                            with patch.object(config, "QUERY_COVERAGE_MIN", 1.5):
                                issues = config.validate_runtime_config()

        self.assertIn("QUERY_COVERAGE_MIN", {issue["name"] for issue in issues})

    def test_validate_runtime_config_requires_chat_model_and_base_url(self):
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "model-key"}):
            with patch.object(config, "MODEL", ""):
                with patch.object(config, "BASE_URL", ""):
                    with patch.object(config, "APP_USERNAME", "admin"):
                        with patch.object(config, "APP_PASSWORD", "strong-local-password"):
                            with patch.object(config, "DATABASE_URL", "postgresql://user:pass@localhost:5432/app"):
                                with patch.object(config, "VECTOR_STORE_BACKEND", "chroma"):
                                    issues = config.validate_runtime_config()

        issue_names = {issue["name"] for issue in issues if issue["severity"] == "error"}
        self.assertIn("CHAT_MODEL", issue_names)
        self.assertIn("CHAT_BASE_URL", issue_names)


if __name__ == "__main__":
    unittest.main()
