import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from scripts import preflight_prod_check


VALID_ENV = """\
DEEPSEEK_API_KEY=sk-real-chat-key
CHAT_MODEL=deepseek-v4-flash
CHAT_BASE_URL=https://api.deepseek.com
EMBEDDING_API_KEY=sk-real-embedding-key
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_MODEL=text-embedding-v4
MILVUS_URI=http://milvus:19530
MILVUS_COLLECTION=ai_agent_vectors
APP_ENV=production
APP_USERNAME=admin
APP_PASSWORD=strong-production-password
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_SAMESITE=lax
POSTGRES_PASSWORD=strong-db-password
DATABASE_URL=postgresql://ai_agent_user:strong-db-password@postgres:5432/ai_agent
DEFAULT_KNOWLEDGE_SOURCE_PATH=/app/knowledge_files
CORS_ALLOWED_ORIGINS=https://example.com
CORS_ALLOW_LOCALHOST_REGEX=false
"""


class PreflightProdCheckTests(unittest.TestCase):
    def write_env(self, content):
        temp_dir = TemporaryDirectory()
        path = Path(temp_dir.name) / ".env.prod"
        path.write_text(content, encoding="utf-8")
        return temp_dir, path

    def test_valid_minimal_production_env_has_no_errors(self):
        temp_dir, path = self.write_env(VALID_ENV)
        self.addCleanup(temp_dir.cleanup)

        result = preflight_prod_check.check_env_file(path)

        self.assertEqual(result.errors, [])

    def test_rejects_placeholders_weak_password_and_localhost_cors(self):
        content = VALID_ENV.replace(
            "sk-real-chat-key",
            "replace_with_real_deepseek_api_key",
        ).replace(
            "strong-production-password",
            "123456",
        ).replace(
            "https://example.com",
            "http://localhost,http://127.0.0.1",
        )
        temp_dir, path = self.write_env(content)
        self.addCleanup(temp_dir.cleanup)

        result = preflight_prod_check.check_env_file(path)

        messages = "\n".join(result.errors)
        self.assertIn("DEEPSEEK_API_KEY still contains a placeholder value.", messages)
        self.assertIn("APP_PASSWORD is too weak for production.", messages)
        self.assertIn("CORS_ALLOWED_ORIGINS must not include localhost in production.", messages)

    def test_rejects_database_password_mismatch(self):
        content = VALID_ENV.replace(
            "postgresql://ai_agent_user:strong-db-password@postgres:5432/ai_agent",
            "postgresql://ai_agent_user:different-password@postgres:5432/ai_agent",
        )
        temp_dir, path = self.write_env(content)
        self.addCleanup(temp_dir.cleanup)

        result = preflight_prod_check.check_env_file(path)

        self.assertIn("POSTGRES_PASSWORD must match the password in DATABASE_URL.", result.errors)

    def test_rejects_localhost_milvus_uri_in_production(self):
        content = VALID_ENV.replace(
            "MILVUS_URI=http://milvus:19530",
            "MILVUS_URI=http://localhost:19530",
        )
        temp_dir, path = self.write_env(content)
        self.addCleanup(temp_dir.cleanup)

        result = preflight_prod_check.check_env_file(path)

        self.assertIn("MILVUS_URI must not point to localhost in production.", result.errors)


if __name__ == "__main__":
    unittest.main()
