import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

import tools
from AI_agent import main, run_agent, run_tool_call


def make_tool_call(name, arguments):
    return SimpleNamespace(
        id=f"call_{name}",
        function=SimpleNamespace(
            name=name,
            arguments=arguments,
        ),
    )


def make_message(content="", tool_calls=None):
    tool_calls = tool_calls or []

    return SimpleNamespace(
        content=content,
        tool_calls=tool_calls,
        model_dump=lambda exclude_none=True: {
            "role": "assistant",
            "content": content,
            **({"tool_calls": tool_calls} if tool_calls else {}),
        },
    )


def make_response(message):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(message=message),
        ],
    )


class RunToolCallTests(unittest.TestCase):
    def test_get_time_returns_result(self):
        tool_call = make_tool_call("get_time", "{}")

        tool_args, tool_result, remaining_lines, denied_by_user = run_tool_call(tool_call, 10)

        self.assertEqual(tool_args, {})
        self.assertRegex(tool_result, r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
        self.assertEqual(remaining_lines, 10)
        self.assertFalse(denied_by_user)

    def test_invalid_json_returns_clear_error(self):
        tool_call = make_tool_call("get_time", "{bad json")

        tool_args, tool_result, remaining_lines, denied_by_user = run_tool_call(tool_call, 10)

        self.assertEqual(tool_args, "{bad json")
        self.assertEqual(
            tool_result,
            "get_time error: tool arguments are not valid JSON.",
        )
        self.assertEqual(remaining_lines, 10)
        self.assertFalse(denied_by_user)

    def test_missing_required_argument_returns_clear_error(self):
        tool_call = make_tool_call("read_file", "{}")

        tool_args, tool_result, remaining_lines, denied_by_user = run_tool_call(tool_call, 10)

        self.assertEqual(tool_args, {})
        self.assertEqual(
            tool_result,
            "read_file error: missing required argument 'path'.",
        )
        self.assertEqual(remaining_lines, 10)
        self.assertFalse(denied_by_user)

    def test_read_file_consumes_remaining_line_budget(self):
        tool_call = make_tool_call(
            "read_file",
            '{"path": "AI_agent.py", "max_lines": 5}',
        )

        tool_args, tool_result, remaining_lines, denied_by_user = run_tool_call(tool_call, 10)

        self.assertEqual(tool_args["max_lines"], 5)
        self.assertIn("Showing AI_agent.py lines 1-5", tool_result)
        self.assertEqual(remaining_lines, 5)
        self.assertFalse(denied_by_user)

    def test_read_file_respects_remaining_line_budget(self):
        tool_call = make_tool_call(
            "read_file",
            '{"path": "AI_agent.py", "max_lines": 20}',
        )

        tool_args, tool_result, remaining_lines, denied_by_user = run_tool_call(tool_call, 7)

        self.assertEqual(tool_args["max_lines"], 7)
        self.assertIn("Showing AI_agent.py lines 1-7", tool_result)
        self.assertEqual(remaining_lines, 0)
        self.assertFalse(denied_by_user)

    def test_read_file_stops_when_budget_is_exhausted(self):
        tool_call = make_tool_call(
            "read_file",
            '{"path": "AI_agent.py", "max_lines": 5}',
        )

        tool_args, tool_result, remaining_lines, denied_by_user = run_tool_call(tool_call, 0)

        self.assertEqual(tool_args["max_lines"], 5)
        self.assertEqual(
            tool_result,
            "read_file error: per-turn file read limit reached. "
            "Ask to continue in the next message.",
        )
        self.assertEqual(remaining_lines, 0)
        self.assertFalse(denied_by_user)

    def test_write_file_requires_confirmation_and_can_be_denied(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            tool_call = make_tool_call(
                "write_file",
                '{"path": "notes.txt", "content": "hello"}',
            )

            with patch.object(tools, "WORKSPACE_ROOT", workspace):
                tool_args, tool_result, remaining_lines, denied_by_user = run_tool_call(
                    tool_call,
                    10,
                    confirm_callback=lambda name, args: False,
                )

            self.assertEqual(tool_args, {"path": "notes.txt", "content": "hello"})
            self.assertEqual(
                tool_result,
                "write_file denied by user. Do not try another file modification tool for this request.",
            )
            self.assertEqual(remaining_lines, 10)
            self.assertTrue(denied_by_user)
            self.assertFalse((workspace / "notes.txt").exists())

    def test_write_file_runs_after_confirmation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            tool_call = make_tool_call(
                "write_file",
                '{"path": "notes.txt", "content": "hello"}',
            )

            with patch.object(tools, "WORKSPACE_ROOT", workspace):
                tool_args, tool_result, remaining_lines, denied_by_user = run_tool_call(
                    tool_call,
                    10,
                    confirm_callback=lambda name, args: True,
                )

            self.assertEqual(tool_args, {"path": "notes.txt", "content": "hello"})
            self.assertEqual(tool_result, "Wrote notes.txt (1 line(s)).")
            self.assertEqual(remaining_lines, 10)
            self.assertFalse(denied_by_user)
            self.assertEqual((workspace / "notes.txt").read_text(encoding="utf-8"), "hello")

    def test_replace_in_file_requires_confirmation_and_can_be_denied(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "notes.txt").write_text("old", encoding="utf-8")
            tool_call = make_tool_call(
                "replace_in_file",
                '{"path": "notes.txt", "old_text": "old", "new_text": "new"}',
            )

            with patch.object(tools, "WORKSPACE_ROOT", workspace):
                tool_args, tool_result, remaining_lines, denied_by_user = run_tool_call(
                    tool_call,
                    10,
                    confirm_callback=lambda name, args: False,
                )

            self.assertEqual(
                tool_args,
                {"path": "notes.txt", "old_text": "old", "new_text": "new"},
            )
            self.assertEqual(
                tool_result,
                "replace_in_file denied by user. Do not try another file modification tool for this request.",
            )
            self.assertEqual(remaining_lines, 10)
            self.assertTrue(denied_by_user)
            self.assertEqual((workspace / "notes.txt").read_text(encoding="utf-8"), "old")

    def test_replace_in_file_runs_after_confirmation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "notes.txt").write_text("old", encoding="utf-8")
            tool_call = make_tool_call(
                "replace_in_file",
                '{"path": "notes.txt", "old_text": "old", "new_text": "new"}',
            )

            with patch.object(tools, "WORKSPACE_ROOT", workspace):
                tool_args, tool_result, remaining_lines, denied_by_user = run_tool_call(
                    tool_call,
                    10,
                    confirm_callback=lambda name, args: True,
                )

            self.assertEqual(
                tool_args,
                {"path": "notes.txt", "old_text": "old", "new_text": "new"},
            )
            self.assertEqual(tool_result, "Replaced 1 occurrence in notes.txt.")
            self.assertEqual(remaining_lines, 10)
            self.assertFalse(denied_by_user)
            self.assertEqual((workspace / "notes.txt").read_text(encoding="utf-8"), "new")

    def test_delete_file_requires_confirmation_and_can_be_denied(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "notes.txt").write_text("hello", encoding="utf-8")
            tool_call = make_tool_call(
                "delete_file",
                '{"path": "notes.txt"}',
            )

            with patch.object(tools, "WORKSPACE_ROOT", workspace):
                tool_args, tool_result, remaining_lines, denied_by_user = run_tool_call(
                    tool_call,
                    10,
                    confirm_callback=lambda name, args: False,
                )

            self.assertEqual(tool_args, {"path": "notes.txt"})
            self.assertEqual(
                tool_result,
                "delete_file denied by user. Do not try another file modification tool for this request.",
            )
            self.assertEqual(remaining_lines, 10)
            self.assertTrue(denied_by_user)
            self.assertTrue((workspace / "notes.txt").exists())

    def test_delete_file_runs_after_confirmation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "notes.txt").write_text("hello", encoding="utf-8")
            tool_call = make_tool_call(
                "delete_file",
                '{"path": "notes.txt"}',
            )

            with patch.object(tools, "WORKSPACE_ROOT", workspace):
                tool_args, tool_result, remaining_lines, denied_by_user = run_tool_call(
                    tool_call,
                    10,
                    confirm_callback=lambda name, args: True,
                )

            self.assertEqual(tool_args, {"path": "notes.txt"})
            self.assertEqual(tool_result, "Deleted notes.txt.")
            self.assertEqual(remaining_lines, 10)
            self.assertFalse(denied_by_user)
            self.assertFalse((workspace / "notes.txt").exists())


class RunAgentTests(unittest.TestCase):
    def test_run_agent_stops_after_user_denies_file_modification(self):
        write_call = make_tool_call(
            "write_file",
            '{"path": "abc.txt", "content": "new", "overwrite": true}',
        )
        first_message = make_message(tool_calls=[write_call])
        second_message = make_message(
            content="I should not be reached",
            tool_calls=[
                make_tool_call(
                    "replace_in_file",
                    '{"path": "abc.txt", "old_text": "old", "new_text": "new"}',
                )
            ],
        )
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=SimpleNamespace(
                        side_effect=None,
                    )
                )
            )
        )
        calls = [make_response(first_message), make_response(second_message)]

        def create_response(**kwargs):
            return calls.pop(0)

        client.chat.completions.create = create_response
        messages = [{"role": "system", "content": "test"}]

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "abc.txt").write_text("old", encoding="utf-8")

            with patch.object(tools, "WORKSPACE_ROOT", workspace):
                with patch("AI_agent.confirm_tool_call", return_value=False):
                    with patch("AI_agent.append_log_entries"):
                        with redirect_stdout(StringIO()):
                            answer = run_agent(client, messages, "change abc")

            self.assertEqual(
                answer,
                "File modification was cancelled. No other write, edit, or delete tool was attempted.",
            )
            self.assertEqual((workspace / "abc.txt").read_text(encoding="utf-8"), "old")
            self.assertEqual(len(calls), 1)

class MainTests(unittest.TestCase):
    def test_main_prints_startup_error_when_api_key_is_missing(self):
        output = StringIO()

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": ""}):
            with redirect_stdout(output):
                main()

        self.assertIn(
            "Startup error: Missing DEEPSEEK_API_KEY. Please set it in .env.",
            output.getvalue(),
        )


if __name__ == "__main__":
    unittest.main()
