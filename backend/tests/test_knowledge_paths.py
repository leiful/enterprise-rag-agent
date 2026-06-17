import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import knowledge


class KnowledgePathTests(unittest.TestCase):
    def test_store_path_value_uses_project_relative_posix_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            target = project_root / "knowledge_files" / "nested" / "notes.md"

            with patch.object(knowledge, "PROJECT_ROOT", project_root):
                self.assertEqual(
                    knowledge.store_path_value(target),
                    "knowledge_files/nested/notes.md",
                )

    def test_source_path_from_metadata_resolves_project_relative_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            target = project_root / "knowledge_files" / "notes.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("hello", encoding="utf-8")

            with patch.object(knowledge, "PROJECT_ROOT", project_root):
                with patch.object(knowledge, "KNOWLEDGE_FILES_DIR", project_root / "knowledge_files"):
                    resolved = knowledge.source_path_from_metadata(
                        "notes.md",
                        {"source_path": "knowledge_files/notes.md"},
                    )

        self.assertEqual(resolved, target.resolve())


if __name__ == "__main__":
    unittest.main()
