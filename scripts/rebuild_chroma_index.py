from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from config import CHROMA_COLLECTION_NAME, CHROMA_PERSIST_DIR  # noqa: E402
import knowledge  # noqa: E402
import vector_store  # noqa: E402


import database  # noqa: E402


def list_active_document_ids() -> list[str]:
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT document_id
            FROM vector_chunks
            GROUP BY document_id
            ORDER BY document_id
            """
        ).fetchall()

    return [row["document_id"] for row in rows]


def resolve_document_path(document_id: str) -> Path:
    project_candidate = PROJECT_ROOT / document_id
    if project_candidate.is_file():
        return project_candidate

    upload_candidate = knowledge.KNOWLEDGE_FILES_DIR / document_id
    if upload_candidate.is_file():
        return upload_candidate

    raise FileNotFoundError(f"Cannot resolve source file for document_id={document_id!r}")


def reset_chroma_storage(reset_storage: bool) -> None:
    if reset_storage and CHROMA_PERSIST_DIR.exists():
        shutil.rmtree(CHROMA_PERSIST_DIR)
    CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
    vector_store.clear_runtime_caches()


def rebuild_documents(document_ids: list[str]) -> list[dict]:
    results = []
    for document_id in document_ids:
        source_path = resolve_document_path(document_id)
        relative_path = source_path.relative_to(PROJECT_ROOT)
        result, error = knowledge.index_file(
            str(relative_path),
            document_id=document_id,
            use_original_name=source_path.parent == knowledge.KNOWLEDGE_FILES_DIR,
            force_reindex=True,
        )
        if error:
            raise RuntimeError(f"Failed to index {document_id}: {error}")
        results.append(result)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild the local Chroma index from active documents.")
    parser.add_argument(
        "--reset-storage",
        action="store_true",
        help="Delete the Chroma persist directory before rebuilding. Use only when no other process is holding the files.",
    )
    args = parser.parse_args()

    document_ids = list_active_document_ids()
    if not document_ids:
        print("No active documents found. Nothing to rebuild.")
        return 0

    print(f"Rebuilding Chroma collection {CHROMA_COLLECTION_NAME!r} at {CHROMA_PERSIST_DIR}")
    print("Documents:", json.dumps(document_ids, ensure_ascii=False))
    reset_chroma_storage(args.reset_storage)
    results = rebuild_documents(document_ids)
    print("Rebuild completed:")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
