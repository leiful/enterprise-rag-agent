import argparse
import json
import re
import shutil
import subprocess
import tarfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


DEFAULT_BACKUPS_DIR = Path("/data/rag-agent/backups")
DEFAULT_KNOWLEDGE_DIR = Path("/data/rag-agent/knowledge")
DEFAULT_RETENTION_COUNT = 14
POSTGRES_CONTAINER = "ai-agent-postgres"
POSTGRES_USER = "ai_agent_user"
POSTGRES_DATABASE = "ai_agent"
CONTAINER_DUMP_PATH = "/tmp/ai_agent.dump"
BACKUP_DIR_PATTERN = re.compile(r"^\d{8}-\d{6}$")


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass
class BackupPlan:
    backup_id: str
    backup_dir: Path
    database_dump: Path
    knowledge_archive: Path
    manifest: Path


@dataclass
class BackupResult:
    plan: BackupPlan
    messages: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self):
        return not self.errors


def run_command(command):
    process = subprocess.run(command, text=True, capture_output=True, check=False)
    return CommandResult(returncode=process.returncode, stdout=process.stdout, stderr=process.stderr)


def build_backup_plan(backups_dir, now=None):
    now = now or datetime.now()
    backup_id = now.strftime("%Y%m%d-%H%M%S")
    backup_dir = Path(backups_dir) / backup_id
    return BackupPlan(
        backup_id=backup_id,
        backup_dir=backup_dir,
        database_dump=backup_dir / "ai_agent.dump",
        knowledge_archive=backup_dir / "knowledge.tar.gz",
        manifest=backup_dir / "manifest.json",
    )


def run_checked(command, runner, errors):
    completed = runner(command)
    if completed.returncode != 0:
        errors.append(f"Command failed: {' '.join(command)}")
        output = completed.stderr.strip() or completed.stdout.strip()
        if output:
            errors.append(output)
    return completed.returncode == 0


def create_knowledge_archive(knowledge_dir, archive_path):
    knowledge_dir = Path(knowledge_dir)
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(knowledge_dir, arcname="knowledge")


def write_manifest(plan, knowledge_dir):
    manifest = {
        "backup_id": plan.backup_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "database_container": POSTGRES_CONTAINER,
        "database_name": POSTGRES_DATABASE,
        "database_dump": plan.database_dump.name,
        "knowledge_dir": str(knowledge_dir),
        "knowledge_archive": plan.knowledge_archive.name,
        "includes_env_prod": False,
        "note": ".env.prod is not copied because it contains production secrets.",
    }
    plan.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def list_managed_backup_dirs(backups_dir):
    backups_dir = Path(backups_dir)
    if not backups_dir.exists():
        return []
    return sorted(
        path
        for path in backups_dir.iterdir()
        if path.is_dir() and BACKUP_DIR_PATTERN.match(path.name)
    )


def cleanup_old_backups(backups_dir, retention_count=DEFAULT_RETENTION_COUNT):
    if retention_count < 1:
        raise ValueError("retention_count must be at least 1.")

    managed_dirs = list_managed_backup_dirs(backups_dir)
    delete_count = max(0, len(managed_dirs) - retention_count)
    deleted = []
    for path in managed_dirs[:delete_count]:
        shutil.rmtree(path)
        deleted.append(path)
    return deleted


def run_backup(
    backups_dir=DEFAULT_BACKUPS_DIR,
    knowledge_dir=DEFAULT_KNOWLEDGE_DIR,
    now=None,
    runner=run_command,
    retention_count=DEFAULT_RETENTION_COUNT,
):
    plan = build_backup_plan(Path(backups_dir), now)
    result = BackupResult(plan=plan)
    knowledge_dir = Path(knowledge_dir)

    if not knowledge_dir.exists():
        result.errors.append("Knowledge directory does not exist.")
        return result
    if not knowledge_dir.is_dir():
        result.errors.append("Knowledge path is not a directory.")
        return result

    plan.backup_dir.mkdir(parents=True, exist_ok=False)

    dump_command = [
        "docker",
        "exec",
        POSTGRES_CONTAINER,
        "pg_dump",
        "-U",
        POSTGRES_USER,
        "-d",
        POSTGRES_DATABASE,
        "-F",
        "c",
        "-f",
        CONTAINER_DUMP_PATH,
    ]
    if not run_checked(dump_command, runner, result.errors):
        return result

    copy_command = [
        "docker",
        "cp",
        f"{POSTGRES_CONTAINER}:{CONTAINER_DUMP_PATH}",
        str(plan.database_dump),
    ]
    if not run_checked(copy_command, runner, result.errors):
        return result

    cleanup_command = ["docker", "exec", POSTGRES_CONTAINER, "rm", "-f", CONTAINER_DUMP_PATH]
    run_checked(cleanup_command, runner, result.errors)

    if result.errors:
        return result

    create_knowledge_archive(knowledge_dir, plan.knowledge_archive)
    write_manifest(plan, knowledge_dir)
    deleted = cleanup_old_backups(plan.backup_dir.parent, retention_count=retention_count)
    result.messages.append(f"Backup created: {plan.backup_dir}")
    if deleted:
        result.messages.append(f"Deleted old backups: {', '.join(str(path) for path in deleted)}")
    return result


def main():
    parser = argparse.ArgumentParser(description="Create a local production backup for PostgreSQL and knowledge files.")
    parser.add_argument("--backups-dir", default=str(DEFAULT_BACKUPS_DIR), help="Host backup directory.")
    parser.add_argument("--knowledge-dir", default=str(DEFAULT_KNOWLEDGE_DIR), help="Host knowledge files directory.")
    parser.add_argument(
        "--retention-count",
        type=int,
        default=DEFAULT_RETENTION_COUNT,
        help="Number of timestamped local backup directories to keep.",
    )
    args = parser.parse_args()

    result = run_backup(
        backups_dir=Path(args.backups_dir),
        knowledge_dir=Path(args.knowledge_dir),
        retention_count=args.retention_count,
    )
    for message in result.messages:
        print(message)
    for error in result.errors:
        print(f"ERROR: {error}")
    if result.ok:
        print("Production local backup completed.")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
