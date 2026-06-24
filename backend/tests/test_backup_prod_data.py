import json
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts import backup_prod_data


class FakeRunner:
    def __init__(self):
        self.commands = []

    def __call__(self, command):
        self.commands.append(command)
        return backup_prod_data.CommandResult(returncode=0, stdout="", stderr="")


class BackupProdDataTests(unittest.TestCase):
    def test_backup_plan_uses_timestamped_directory(self):
        now = datetime(2026, 6, 24, 2, 0, 0)

        plan = backup_prod_data.build_backup_plan(Path("/data/rag-agent/backups"), now)

        self.assertEqual(plan.backup_dir, Path("/data/rag-agent/backups/20260624-020000"))
        self.assertEqual(plan.database_dump, Path("/data/rag-agent/backups/20260624-020000/ai_agent.dump"))
        self.assertEqual(plan.knowledge_archive, Path("/data/rag-agent/backups/20260624-020000/knowledge.tar.gz"))
        self.assertEqual(plan.manifest, Path("/data/rag-agent/backups/20260624-020000/manifest.json"))

    def test_run_backup_creates_dump_archive_and_manifest(self):
        runner = FakeRunner()
        now = datetime(2026, 6, 24, 2, 0, 0)
        with TemporaryDirectory() as temp_dir:
            backups_dir = Path(temp_dir) / "backups"
            knowledge_dir = Path(temp_dir) / "knowledge"
            knowledge_dir.mkdir()

            result = backup_prod_data.run_backup(
                backups_dir=backups_dir,
                knowledge_dir=knowledge_dir,
                now=now,
                runner=runner,
            )

            manifest = json.loads(result.plan.manifest.read_text(encoding="utf-8"))
            archive_exists = result.plan.knowledge_archive.exists()

        self.assertTrue(result.ok)
        self.assertEqual(
            runner.commands[0],
            [
                "docker",
                "exec",
                "ai-agent-postgres",
                "pg_dump",
                "-U",
                "ai_agent_user",
                "-d",
                "ai_agent",
                "-F",
                "c",
                "-f",
                "/tmp/ai_agent.dump",
            ],
        )
        self.assertEqual(
            runner.commands[1],
            [
                "docker",
                "cp",
                "ai-agent-postgres:/tmp/ai_agent.dump",
                str(result.plan.database_dump),
            ],
        )
        self.assertEqual(
            runner.commands[2],
            [
                "docker",
                "exec",
                "ai-agent-postgres",
                "rm",
                "-f",
                "/tmp/ai_agent.dump",
            ],
        )
        self.assertTrue(archive_exists)
        self.assertEqual(manifest["backup_id"], "20260624-020000")
        self.assertEqual(manifest["database_dump"], "ai_agent.dump")
        self.assertEqual(manifest["knowledge_archive"], "knowledge.tar.gz")
        self.assertFalse(manifest["includes_env_prod"])

    def test_backup_fails_when_knowledge_directory_is_missing(self):
        with TemporaryDirectory() as temp_dir:
            result = backup_prod_data.run_backup(
                backups_dir=Path(temp_dir) / "backups",
                knowledge_dir=Path(temp_dir) / "missing",
                now=datetime(2026, 6, 24, 2, 0, 0),
                runner=FakeRunner(),
            )

        self.assertFalse(result.ok)
        self.assertIn("Knowledge directory does not exist.", result.errors)

    def test_cleanup_old_backups_keeps_recent_timestamped_directories(self):
        with TemporaryDirectory() as temp_dir:
            backups_dir = Path(temp_dir)
            for name in ["20260620-020000", "20260621-020000", "20260622-020000"]:
                (backups_dir / name).mkdir()
            (backups_dir / "manual-backup").mkdir()
            (backups_dir / "backup.log").write_text("keep me", encoding="utf-8")

            deleted = backup_prod_data.cleanup_old_backups(backups_dir, retention_count=2)

            self.assertEqual(deleted, [backups_dir / "20260620-020000"])
            self.assertFalse((backups_dir / "20260620-020000").exists())
            self.assertTrue((backups_dir / "20260621-020000").exists())
            self.assertTrue((backups_dir / "20260622-020000").exists())
            self.assertTrue((backups_dir / "manual-backup").exists())
            self.assertTrue((backups_dir / "backup.log").exists())

    def test_run_backup_applies_retention_after_successful_backup(self):
        runner = FakeRunner()
        now = datetime(2026, 6, 24, 2, 0, 0)
        with TemporaryDirectory() as temp_dir:
            backups_dir = Path(temp_dir) / "backups"
            knowledge_dir = Path(temp_dir) / "knowledge"
            knowledge_dir.mkdir()
            for name in ["20260620-020000", "20260621-020000"]:
                (backups_dir / name).mkdir(parents=True)

            result = backup_prod_data.run_backup(
                backups_dir=backups_dir,
                knowledge_dir=knowledge_dir,
                now=now,
                runner=runner,
                retention_count=2,
            )

            remaining = sorted(path.name for path in backups_dir.iterdir())

        self.assertTrue(result.ok)
        self.assertEqual(remaining, ["20260621-020000", "20260624-020000"])


if __name__ == "__main__":
    unittest.main()
