import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tools


class ToolsTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.addCleanup(self.temp_dir.cleanup)

        (self.workspace / "notes.txt").write_text(
            "alpha\nbeta keyword\ngamma keyword\n",
            encoding="utf-8",
        )
        (self.workspace / "script.py").write_text(
            "print('hello')\n# keyword\n",
            encoding="utf-8",
        )
        (self.workspace / ".env").write_text("SECRET=value\n", encoding="utf-8")
        (self.workspace / "image.png").write_bytes(b"not text")

        self.workspace_patch = patch.object(tools, "WORKSPACE_ROOT", self.workspace)
        self.workspace_patch.start()
        self.addCleanup(self.workspace_patch.stop)


class ListFilesTests(ToolsTestCase):
    def test_list_files_only_includes_readable_project_files(self):
        result = tools.list_files()

        self.assertIn("notes.txt", result)
        self.assertIn("script.py", result)
        self.assertNotIn(".env", result)
        self.assertNotIn("image.png", result)


class FindFilesTests(ToolsTestCase):
    def test_find_files_finds_readable_files_by_name_case_insensitively(self):
        result = tools.find_files("NOTES")

        self.assertIn("Found 1 file match(es) for 'NOTES'.", result)
        self.assertIn("notes.txt", result)
        self.assertNotIn(".env", result)
        self.assertNotIn("image.png", result)

    def test_find_files_requires_query(self):
        result = tools.find_files("")

        self.assertEqual(result, "find_files error: query is required")

    def test_find_files_reports_no_matches(self):
        result = tools.find_files("missing")

        self.assertEqual(result, "No files found for 'missing'.")


class ResolveReadableFileTests(ToolsTestCase):
    def test_resolve_readable_file_rejects_path_outside_workspace(self):
        outside_file = self.workspace.parent / "outside.txt"
        outside_file.write_text("secret\n", encoding="utf-8")

        target, error = tools.resolve_readable_file("../outside.txt")

        self.assertIsNone(target)
        self.assertEqual(error, "path is outside workspace: ../outside.txt")

    def test_resolve_readable_file_rejects_excluded_files(self):
        target, error = tools.resolve_readable_file(".env")

        self.assertIsNone(target)
        self.assertEqual(error, "file is not allowed: .env")

    def test_resolve_readable_file_rejects_disallowed_extensions(self):
        target, error = tools.resolve_readable_file("image.png")

        self.assertIsNone(target)
        self.assertEqual(error, "file is not allowed: image.png")


class ReadFileTests(ToolsTestCase):
    def test_read_file_returns_numbered_lines(self):
        result = tools.read_file("notes.txt", max_lines=2)

        self.assertIn("Showing notes.txt lines 1-2 of 3.", result)
        self.assertIn("1: alpha", result)
        self.assertIn("2: beta keyword", result)
        self.assertIn("More lines are available from line 3.", result)

    def test_read_file_normalizes_start_line_below_one(self):
        result = tools.read_file("notes.txt", start_line=0, max_lines=1)

        self.assertIn("Showing notes.txt lines 1-1 of 3.", result)
        self.assertIn("1: alpha", result)

    def test_read_file_reports_start_line_beyond_file_length(self):
        result = tools.read_file("notes.txt", start_line=10)

        self.assertEqual(
            result,
            "read_file error: start_line 10 is beyond file length 3",
        )

    def test_read_file_reports_disallowed_file(self):
        result = tools.read_file(".env")

        self.assertEqual(result, "read_file error: file is not allowed: .env")


class WriteFileTests(ToolsTestCase):
    def test_write_file_creates_text_file(self):
        result = tools.write_file("new_notes.txt", "hello\nworld\n")

        self.assertEqual(result, "Wrote new_notes.txt (2 line(s)).")
        self.assertEqual(
            (self.workspace / "new_notes.txt").read_text(encoding="utf-8"),
            "hello\nworld\n",
        )

    def test_write_file_does_not_overwrite_by_default(self):
        result = tools.write_file("notes.txt", "replacement")

        self.assertEqual(
            result,
            "write_file error: file already exists: notes.txt. Set overwrite=true to replace it.",
        )
        self.assertIn("alpha", (self.workspace / "notes.txt").read_text(encoding="utf-8"))

    def test_write_file_overwrites_when_requested(self):
        result = tools.write_file("notes.txt", "replacement", overwrite=True)

        self.assertEqual(result, "Wrote notes.txt (1 line(s)).")
        self.assertEqual(
            (self.workspace / "notes.txt").read_text(encoding="utf-8"),
            "replacement",
        )

    def test_write_file_rejects_excluded_files(self):
        result = tools.write_file(".env", "SECRET=new")

        self.assertEqual(result, "write_file error: file is not allowed: .env")

    def test_write_file_rejects_disallowed_extensions(self):
        result = tools.write_file("image.png", "not really an image", overwrite=True)

        self.assertEqual(result, "write_file error: file extension is not allowed: image.png")


class ReplaceInFileTests(ToolsTestCase):
    def test_replace_in_file_replaces_exactly_one_match(self):
        result = tools.replace_in_file("notes.txt", "beta keyword", "beta replaced")

        self.assertEqual(result, "Replaced 1 occurrence in notes.txt.")
        self.assertEqual(
            (self.workspace / "notes.txt").read_text(encoding="utf-8"),
            "alpha\nbeta replaced\ngamma keyword\n",
        )

    def test_replace_in_file_rejects_missing_old_text(self):
        result = tools.replace_in_file("notes.txt", "missing", "new")

        self.assertEqual(result, "replace_in_file error: old_text not found.")

    def test_replace_in_file_rejects_empty_old_text(self):
        result = tools.replace_in_file("notes.txt", "", "new")

        self.assertEqual(result, "replace_in_file error: old_text is required")

    def test_replace_in_file_rejects_multiple_matches(self):
        result = tools.replace_in_file("notes.txt", "keyword", "new")

        self.assertEqual(
            result,
            "replace_in_file error: old_text matched 2 times. Make it more specific.",
        )
        self.assertIn("beta keyword", (self.workspace / "notes.txt").read_text(encoding="utf-8"))

    def test_replace_in_file_rejects_excluded_files(self):
        result = tools.replace_in_file(".env", "SECRET", "PUBLIC")

        self.assertEqual(result, "replace_in_file error: file is not allowed: .env")


class DeleteFileTests(ToolsTestCase):
    def test_delete_file_deletes_readable_file(self):
        result = tools.delete_file("notes.txt")

        self.assertEqual(result, "Deleted notes.txt.")
        self.assertFalse((self.workspace / "notes.txt").exists())

    def test_delete_file_rejects_missing_file(self):
        result = tools.delete_file("missing.txt")

        self.assertEqual(result, "delete_file error: file not found: missing.txt")

    def test_delete_file_rejects_excluded_files(self):
        result = tools.delete_file(".env")

        self.assertEqual(result, "delete_file error: file is not allowed: .env")
        self.assertTrue((self.workspace / ".env").exists())

    def test_delete_file_rejects_disallowed_extensions(self):
        result = tools.delete_file("image.png")

        self.assertEqual(result, "delete_file error: file is not allowed: image.png")
        self.assertTrue((self.workspace / "image.png").exists())

    def test_delete_file_rejects_directories(self):
        (self.workspace / "docs").mkdir()

        result = tools.delete_file("docs")

        self.assertEqual(result, "delete_file error: file not found: docs")
        self.assertTrue((self.workspace / "docs").is_dir())


class SearchFileTests(ToolsTestCase):
    def test_search_file_finds_matches_case_insensitively(self):
        result = tools.search_file("notes.txt", "KEYWORD", max_matches=1)

        self.assertIn("Found 1 match(es) for 'KEYWORD' in notes.txt.", result)
        self.assertIn("2: beta keyword", result)
        self.assertNotIn("3: gamma keyword", result)

    def test_search_file_requires_query(self):
        result = tools.search_file("notes.txt", "")

        self.assertEqual(result, "search_file error: query is required")

    def test_search_file_reports_no_matches(self):
        result = tools.search_file("notes.txt", "missing")

        self.assertEqual(result, "No matches for 'missing' in notes.txt.")


class SearchFilesTests(ToolsTestCase):
    def test_search_files_finds_matches_across_readable_files(self):
        result = tools.search_files("keyword", max_matches=3)

        self.assertIn("Found 3 project match(es) for 'keyword'.", result)
        self.assertIn("notes.txt:2: beta keyword", result)
        self.assertIn("notes.txt:3: gamma keyword", result)
        self.assertIn("script.py:2: # keyword", result)

    def test_search_files_requires_query(self):
        result = tools.search_files("")

        self.assertEqual(result, "search_files error: query is required")


class CallToolTests(ToolsTestCase):
    def test_call_tool_routes_known_tool(self):
        result = tools.call_tool("read_file", {"path": "notes.txt", "max_lines": 1})

        self.assertIn("Showing notes.txt lines 1-1 of 3.", result)

    def test_call_tool_routes_run_tests(self):
        with patch("tools.run_tests", return_value="Tests passed."):
            result = tools.call_tool("run_tests", {"timeout_seconds": 30})

        self.assertIn("Tests passed.", result)

    def test_call_tool_reports_unknown_tool(self):
        result = tools.call_tool("missing_tool", {})

        self.assertEqual(result, "unknown tool: missing_tool")


class RunTestsToolTests(unittest.TestCase):
    def test_truncate_output_keeps_short_output(self):
        self.assertEqual(tools.truncate_output("short", max_chars=10), "short")

    def test_truncate_output_marks_long_output(self):
        self.assertEqual(
            tools.truncate_output("abcdefghij", max_chars=5),
            "abcde\n... output truncated ...",
        )


class ToolSchemaTests(unittest.TestCase):
    def test_schema_names_match_supported_tools(self):
        schema_names = {
            tool["function"]["name"]
            for tool in tools.TOOLS
        }

        self.assertEqual(
            schema_names,
            {
                "get_time",
                "list_files",
                "find_files",
                "read_file",
                "write_file",
                "replace_in_file",
                "delete_file",
                "search_file",
                "run_tests",
                "search_files",
            },
        )

    def test_read_and_search_schemas_require_arguments(self):
        schemas_by_name = {
            tool["function"]["name"]: tool["function"]["parameters"]
            for tool in tools.TOOLS
        }

        self.assertEqual(
            schemas_by_name["read_file"]["required"],
            ["path"],
        )
        self.assertEqual(
            schemas_by_name["write_file"]["required"],
            ["path", "content"],
        )
        self.assertEqual(
            schemas_by_name["replace_in_file"]["required"],
            ["path", "old_text", "new_text"],
        )
        self.assertEqual(
            schemas_by_name["delete_file"]["required"],
            ["path"],
        )
        self.assertEqual(
            schemas_by_name["search_file"]["required"],
            ["path", "query"],
        )
        self.assertEqual(
            schemas_by_name["find_files"]["required"],
            ["query"],
        )


if __name__ == "__main__":
    unittest.main()
