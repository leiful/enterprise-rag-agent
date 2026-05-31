import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import memory


class MemoryLoadSaveTests(unittest.TestCase):
    def test_load_messages_returns_system_message_when_history_is_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            history_file = Path(temp_dir) / "missing_history.json"

            with patch.object(memory, "HISTORY_FILE", str(history_file)):
                messages = memory.load_messages()

        self.assertEqual(messages, [memory.SYSTEM_MESSAGE])
        self.assertIsNot(messages[0], memory.SYSTEM_MESSAGE)

    def test_load_messages_returns_system_message_when_history_is_invalid_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            history_file = Path(temp_dir) / "chat_history.json"
            history_file.write_text("{bad json", encoding="utf-8")

            with patch.object(memory, "HISTORY_FILE", str(history_file)):
                messages = memory.load_messages()

        self.assertEqual(messages, [memory.SYSTEM_MESSAGE])

    def test_load_messages_inserts_system_message_when_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            history_file = Path(temp_dir) / "chat_history.json"
            history_file.write_text(
                json.dumps([{"role": "user", "content": "hello"}]),
                encoding="utf-8",
            )

            with patch.object(memory, "HISTORY_FILE", str(history_file)):
                messages = memory.load_messages()

        self.assertEqual(messages[0], memory.SYSTEM_MESSAGE)
        self.assertEqual(messages[1], {"role": "user", "content": "hello"})

    def test_save_messages_writes_json_history(self):
        messages = [
            memory.SYSTEM_MESSAGE.copy(),
            {"role": "user", "content": "hello"},
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            history_file = Path(temp_dir) / "chat_history.json"

            with patch.object(memory, "HISTORY_FILE", str(history_file)):
                memory.save_messages(messages)

            saved = json.loads(history_file.read_text(encoding="utf-8"))

        self.assertEqual(saved, messages)


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
