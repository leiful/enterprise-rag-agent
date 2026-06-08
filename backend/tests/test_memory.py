import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app_logging
import memory


class MemoryLogTests(unittest.TestCase):
    def test_append_log_entries_writes_json_lines(self):
        entries = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "chat_log.jsonl"

            with patch.object(memory, "LOG_FILE", str(log_file)):
                memory.append_log_entries(entries)

            records = [
                json.loads(line)
                for line in log_file.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual([record["message"] for record in records], entries)
        self.assertTrue(all("timestamp" in record for record in records))

    def test_structured_log_event_writes_jsonl(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            app_log = Path(temp_dir) / "app.jsonl"
            error_log = Path(temp_dir) / "errors.jsonl"

            with (
                patch.object(app_logging, "LOG_DIR", Path(temp_dir)),
                patch.object(app_logging, "APP_LOG_FILE", app_log),
                patch.object(app_logging, "ERROR_LOG_FILE", error_log),
                patch.object(app_logging, "_CONFIGURED", False),
            ):
                try:
                    logger = app_logging.get_logger("test.structured")
                    app_logging.log_event(
                        logger,
                        20,
                        "test_event",
                        user_id=1,
                        api_key="secret",
                    )
                finally:
                    app_logging.reset_logging_for_tests()

            records = [
                json.loads(line)
                for line in app_log.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(records[-1]["event"], "test_event")
        self.assertEqual(records[-1]["user_id"], 1)
        self.assertEqual(records[-1]["api_key"], "[REDACTED]")


class TrimMessagesTests(unittest.TestCase):
    def test_trim_messages_keeps_system_and_recent_history(self):
        messages = [
            memory.SYSTEM_MESSAGE.copy(),
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "old reply"},
            {"role": "user", "content": "new"},
        ]

        with patch.object(memory, "MAX_HISTORY_MESSAGES", 2):
            memory.trim_messages(messages)

        self.assertEqual(
            messages,
            [
                memory.SYSTEM_MESSAGE,
                {"role": "assistant", "content": "old reply"},
                {"role": "user", "content": "new"},
            ],
        )

    def test_trim_messages_does_not_start_with_tool_message(self):
        messages = [
            memory.SYSTEM_MESSAGE.copy(),
            {"role": "user", "content": "old"},
            {"role": "tool", "tool_call_id": "1", "content": "result"},
            {"role": "assistant", "content": "done"},
        ]

        with patch.object(memory, "MAX_HISTORY_MESSAGES", 2):
            memory.trim_messages(messages)

        self.assertEqual(
            messages,
            [
                memory.SYSTEM_MESSAGE,
                {"role": "assistant", "content": "done"},
            ],
        )

    def test_trim_messages_does_not_start_mid_tool_call(self):
        assistant_tool_call = {
            "role": "assistant",
            "tool_calls": [{"id": "1"}],
        }
        messages = [
            memory.SYSTEM_MESSAGE.copy(),
            {"role": "user", "content": "old"},
            assistant_tool_call,
            {"role": "tool", "tool_call_id": "1", "content": "result"},
            {"role": "assistant", "content": "done"},
        ]

        with patch.object(memory, "MAX_HISTORY_MESSAGES", 3):
            memory.trim_messages(messages)

        self.assertEqual(
            messages,
            [
                memory.SYSTEM_MESSAGE,
                {"role": "assistant", "content": "done"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
