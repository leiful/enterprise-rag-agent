# -*- coding: utf-8 -*-

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import database
import knowledge
import vector_store
from config import DEFAULT_KNOWLEDGE_SOURCE_PATH


LOCAL_FOLDER = "local_folder"


def utc_from_timestamp(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def format_source(source):
    result = dict(source)
    raw_result = result.pop("last_sync_result_json", None)
    if raw_result:
        try:
            import json

            result["last_sync_result"] = json.loads(raw_result)
        except Exception:
            result["last_sync_result"] = None
    else:
        result["last_sync_result"] = None
    return result


def ensure_default_local_source():
    source = database.upsert_knowledge_source(
        "Local folder",
        LOCAL_FOLDER,
        knowledge.store_path_value(DEFAULT_KNOWLEDGE_SOURCE_PATH),
        enabled=True,
    )
    return format_source(source)


def list_sources():
    sources = database.list_knowledge_sources()
    if not sources:
        ensure_default_local_source()
        sources = database.list_knowledge_sources()
    results = []
    for source in sources:
        formatted = format_source(source)
        files = database.list_knowledge_source_files(source["id"])
        counts = {}
        for file in files:
            counts[file["status"]] = counts.get(file["status"], 0) + 1
        formatted["file_status_counts"] = counts
        formatted["recent_files"] = sorted(
            files,
            key=lambda item: item.get("updated_at") or "",
            reverse=True,
        )[:10]
        results.append(formatted)
    return results


def sync_source(source_id, enqueue_index):
    source = database.get_knowledge_source(source_id)
    if not source:
        return None, "source not found"
    if source["type"] != LOCAL_FOLDER:
        return None, f"unsupported source type: {source['type']}"
    if not source["enabled"]:
        return None, "source is disabled"

    root = knowledge.resolve_project_path(source["path"])
    if not root.is_dir():
        return None, f"source path is not a directory: {source['path']}"

    known_files = {
        row["path"]: row
        for row in database.list_knowledge_source_files(source_id)
    }
    seen_paths = set()
    queued_jobs = []
    unchanged = 0
    skipped = 0

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in knowledge.ALLOWED_KNOWLEDGE_EXTENSIONS:
            skipped += 1
            continue

        relative_source_path = path.relative_to(root).as_posix()
        path_parts = Path(relative_source_path).parts
        department = path_parts[0] if len(path_parts) > 1 else None
        seen_paths.add(relative_source_path)
        content_hash = file_hash(path)
        stat = path.stat()
        modified_at = utc_from_timestamp(stat.st_mtime)
        document_id = f"source-{source_id}__{relative_source_path.replace('/', '__')}"
        previous = known_files.get(relative_source_path)
        duplicate_document_id = vector_store.find_document_by_content_hash(
            content_hash,
            exclude_document_id=document_id,
        )
        if duplicate_document_id:
            vector_store.delete_document(document_id)
            database.upsert_knowledge_source_file(
                source_id,
                document_id=duplicate_document_id,
                path=relative_source_path,
                content_hash=content_hash,
                file_size=stat.st_size,
                modified_at=modified_at,
                status="indexed",
                last_index_job_id=previous.get("last_index_job_id") if previous else None,
                owns_index=False,
            )
            unchanged += 1
            continue

        has_chunks = bool(vector_store.list_document_chunks(document_id))
        if (
            previous
            and previous.get("content_hash") == content_hash
            and previous.get("status") == "indexed"
            and has_chunks
        ):
            unchanged += 1
            continue

        relative_project_path = knowledge.store_path_value(path)
        job_id = enqueue_index(
            path=relative_project_path,
            document_id=document_id,
            notes=None,
            category=source["name"],
            tags=["source", source["type"]],
            metadata={"department": department} if department else None,
            use_original_name=False,
            force_reindex=True,
        )
        database.upsert_knowledge_source_file(
            source_id,
            document_id=document_id,
            path=relative_source_path,
            content_hash=content_hash,
            file_size=stat.st_size,
            modified_at=modified_at,
            status="queued",
            last_index_job_id=job_id,
            owns_index=True,
        )
        job = database.get_index_job(job_id)
        if job and job.get("status") == "completed":
            database.update_knowledge_source_file_by_job(job_id, "indexed")
        elif job and job.get("status") == "failed":
            database.update_knowledge_source_file_by_job(job_id, "failed")
        queued_jobs.append({
            "job_id": job_id,
            "document_id": document_id,
            "path": relative_source_path,
        })

    missing = []
    for relative_source_path, row in known_files.items():
        if relative_source_path in seen_paths:
            continue
        if row.get("owns_index", True):
            vector_store.delete_document(row["document_id"])
        database.upsert_knowledge_source_file(
            source_id,
            document_id=row["document_id"],
            path=relative_source_path,
            content_hash=row.get("content_hash"),
            file_size=row.get("file_size"),
            modified_at=row.get("modified_at"),
            status="missing",
            last_index_job_id=row.get("last_index_job_id"),
        )
        missing.append({
            "document_id": row["document_id"],
            "path": relative_source_path,
        })

    result = {
        "queued_count": len(queued_jobs),
        "unchanged_count": unchanged,
        "missing_count": len(missing),
        "skipped_count": skipped,
        "jobs": queued_jobs,
        "missing_documents": missing,
        "removed_index_count": len(missing),
    }
    database.update_knowledge_source_sync(source_id, result)
    return result, None
