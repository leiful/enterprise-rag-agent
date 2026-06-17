import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import knowledge
import knowledge_sources


class KnowledgeSourceTests(unittest.TestCase):
    def test_default_local_source_uses_configured_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            configured_path = project_root / "enterprise_docs"
            source = {
                "id": 1,
                "name": "Local folder",
                "type": knowledge_sources.LOCAL_FOLDER,
                "path": "enterprise_docs",
                "enabled": True,
                "last_sync_result_json": None,
            }
            with patch.object(knowledge_sources, "DEFAULT_KNOWLEDGE_SOURCE_PATH", configured_path):
                with patch.object(knowledge, "PROJECT_ROOT", project_root):
                    with patch.object(knowledge, "KNOWLEDGE_FILES_DIR", project_root / "knowledge_files"):
                        with patch("knowledge_sources.database.upsert_knowledge_source", return_value=source) as upsert_source:
                            result = knowledge_sources.ensure_default_local_source()

        upsert_source.assert_called_once_with(
            "Local folder",
            knowledge_sources.LOCAL_FOLDER,
            "enterprise_docs",
            enabled=True,
        )
        self.assertEqual(result["path"], "enterprise_docs")

    def test_sync_source_removes_indexes_for_missing_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = {
                "id": 7,
                "name": "Policies",
                "type": knowledge_sources.LOCAL_FOLDER,
                "path": temp_dir,
                "enabled": True,
            }
            known_files = [
                {
                    "document_id": "source-7__old.md",
                    "path": "old.md",
                    "content_hash": "old-hash",
                    "file_size": 12,
                    "modified_at": "2026-01-01T00:00:00+00:00",
                    "last_index_job_id": "job-old",
                }
            ]

            with patch("knowledge_sources.database.get_knowledge_source", return_value=source):
                with patch("knowledge_sources.database.list_knowledge_source_files", return_value=known_files):
                    with patch("knowledge_sources.database.upsert_knowledge_source_file") as upsert_file:
                        with patch("knowledge_sources.database.update_knowledge_source_sync") as update_sync:
                            with patch("knowledge_sources.vector_store.delete_document") as delete_document:
                                result, error = knowledge_sources.sync_source(7, lambda **kwargs: "job-new")

        self.assertIsNone(error)
        self.assertEqual(result["missing_count"], 1)
        self.assertEqual(result["removed_index_count"], 1)
        self.assertEqual(result["missing_documents"][0]["document_id"], "source-7__old.md")
        delete_document.assert_called_once_with("source-7__old.md")
        upsert_file.assert_called_once()
        update_sync.assert_called_once()

    def test_sync_source_reuses_existing_document_for_duplicate_content(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "notes.md"
            path.write_text("same content", encoding="utf-8")
            source = {
                "id": 7,
                "name": "Policies",
                "type": knowledge_sources.LOCAL_FOLDER,
                "path": temp_dir,
                "enabled": True,
            }

            with patch("knowledge_sources.database.get_knowledge_source", return_value=source):
                with patch("knowledge_sources.database.list_knowledge_source_files", return_value=[]):
                    with patch("knowledge_sources.vector_store.find_document_by_content_hash", return_value="notes.md"):
                        with patch("knowledge_sources.vector_store.delete_document") as delete_document:
                            with patch("knowledge_sources.database.upsert_knowledge_source_file") as upsert_file:
                                with patch("knowledge_sources.database.update_knowledge_source_sync") as update_sync:
                                    result, error = knowledge_sources.sync_source(7, lambda **kwargs: "job-new")

        self.assertIsNone(error)
        self.assertEqual(result["queued_count"], 0)
        self.assertEqual(result["unchanged_count"], 1)
        delete_document.assert_called_once_with("source-7__notes.md")
        upsert_file.assert_called_once()
        self.assertEqual(upsert_file.call_args.kwargs["document_id"], "notes.md")
        self.assertFalse(upsert_file.call_args.kwargs["owns_index"])
        update_sync.assert_called_once()


if __name__ == "__main__":
    unittest.main()
