import json
import unittest
from unittest.mock import patch

from scripts import verify_prod_deploy


def completed(stdout="", returncode=0):
    return verify_prod_deploy.CommandResult(returncode=returncode, stdout=stdout, stderr="")


class VerifyProdDeployTests(unittest.TestCase):
    def test_container_check_passes_when_service_is_running_and_healthy(self):
        runner = lambda command: completed(stdout=json.dumps({"Status": "running", "Health": {"Status": "healthy"}}))

        result = verify_prod_deploy.check_container("backend", "ai-agent-backend", runner)

        self.assertEqual(result.errors, [])
        self.assertIn("backend container is running and healthy.", result.messages)

    def test_container_check_fails_when_health_is_unhealthy(self):
        runner = lambda command: completed(stdout=json.dumps({"Status": "running", "Health": {"Status": "unhealthy"}}))

        result = verify_prod_deploy.check_container("backend", "ai-agent-backend", runner)

        self.assertIn("backend container health is unhealthy.", result.errors)

    def test_compose_ps_requires_all_services(self):
        runner = lambda command: completed(stdout="ai-agent-postgres\nai-agent-backend\n")

        result = verify_prod_deploy.check_compose_services(runner)

        self.assertIn("compose ps output does not include ai-agent-nginx.", result.errors)

    def test_http_health_uses_configured_url(self):
        with patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.status = 200

            result = verify_prod_deploy.check_http_health("https://example.com/health")

        self.assertEqual(result.errors, [])
        self.assertIn("HTTP health check passed: https://example.com/health", result.messages)


if __name__ == "__main__":
    unittest.main()
