import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_file = str(Path(self.temp_dir.name) / "test-agent.db")
        self.database_patch = patch.object(database, "DATABASE_FILE", self.database_file)
        self.username_patch = patch.object(database, "APP_USERNAME", "admin")
        self.password_patch = patch.object(database, "APP_PASSWORD", "password")

        self.database_patch.start()
        self.username_patch.start()
        self.password_patch.start()

    def tearDown(self):
        self.password_patch.stop()
        self.username_patch.stop()
        self.database_patch.stop()
        self.temp_dir.cleanup()

    def test_init_db_creates_default_user(self):
        database.init_db()

        user = database.authenticate_user("admin", "password")

        self.assertIsNotNone(user)
        self.assertEqual(user["username"], "admin")

    def test_password_hash_does_not_store_plain_text_password(self):
        password_hash = database.hash_password("password")

        self.assertNotIn("password", password_hash)
        self.assertTrue(database.verify_password("password", password_hash))
        self.assertFalse(database.verify_password("wrong", password_hash))

    def test_create_and_get_session(self):
        database.init_db()
        user = database.authenticate_user("admin", "password")

        database.create_session("session-1", user["id"], expires_at=200)
        session = database.get_session("session-1", now=100)

        self.assertEqual(session["username"], "admin")
        self.assertEqual(session["expires_at"], 200)

    def test_expired_session_is_removed(self):
        database.init_db()
        user = database.authenticate_user("admin", "password")
        database.create_session("session-1", user["id"], expires_at=100)

        session = database.get_session("session-1", now=101)

        self.assertIsNone(session)
        self.assertIsNone(database.get_session("session-1", now=101))

    def test_create_and_list_conversation_messages(self):
        database.init_db()
        user = database.authenticate_user("admin", "password")
        conversation_id = database.create_conversation(user["id"], "Hello")

        database.add_message(conversation_id, "user", "hi")
        database.add_message(conversation_id, "assistant", "hello")

        conversations = database.list_conversations(user["id"])
        messages = database.list_messages(user["id"], conversation_id)

        self.assertEqual(conversations[0]["id"], conversation_id)
        self.assertEqual(conversations[0]["title"], "Hello")
        self.assertEqual(
            [(message["role"], message["content"]) for message in messages],
            [("user", "hi"), ("assistant", "hello")],
        )

    def test_get_conversation_rejects_other_user(self):
        database.init_db()
        admin = database.authenticate_user("admin", "password")
        other_id = database.create_conversation(admin["id"], "Private")

        self.assertIsNone(database.get_conversation(admin["id"] + 1, other_id))


if __name__ == "__main__":
    unittest.main()
