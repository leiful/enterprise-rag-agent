import unittest
from unittest.mock import patch

import database
from tests.test_db_utils import patched_postgres_database, reset_test_database


class DatabaseConnectionTests(unittest.TestCase):
    def test_connect_sets_short_connect_timeout(self):
        with patch.object(database, "DATABASE_URL", "postgresql://user:pass@localhost:5432/app"):
            with patch.object(database.psycopg, "connect") as connect_mock:
                connection = connect_mock.return_value

                with database.connect() as result:
                    self.assertIs(result, connection)

        connect_mock.assert_called_once_with(
            "postgresql://user:pass@localhost:5432/app",
            row_factory=database.dict_row,
            connect_timeout=database.DATABASE_CONNECT_TIMEOUT_SECONDS,
        )
        connection.commit.assert_called_once()
        connection.close.assert_called_once()


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.database_context = patched_postgres_database()
        self.database_context.__enter__()

    def tearDown(self):
        self.database_context.__exit__(None, None, None)

    def reset_db(self):
        reset_test_database()
        database.init_db()

    def test_init_db_creates_default_user(self):
        self.reset_db()

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

    def test_create_and_delete_department(self):
        database.init_db()

        department = database.create_department(" Finance ")
        departments = database.list_departments()
        deleted = database.delete_department(department["id"])

        self.assertEqual(department["name"], "Finance")
        self.assertEqual([item["name"] for item in departments], ["Finance"])
        self.assertTrue(deleted)
        self.assertEqual(database.list_departments(), [])

    def test_add_and_summarize_rag_feedback(self):
        database.init_db()
        user = database.authenticate_user("admin", "password")
        conversation_id = database.create_conversation(user["id"], "Feedback")

        feedback_id = database.add_rag_feedback(
            user,
            "wrong_source",
            conversation_id=conversation_id,
            query="Which port?",
            answer="Use 5173.",
            sources=[{"document_id": "notes.md"}],
        )

        feedback = database.list_rag_feedback()
        summary = database.summarize_rag_feedback()

        self.assertEqual(feedback[0]["id"], feedback_id)
        self.assertEqual(feedback[0]["sources"][0]["document_id"], "notes.md")
        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["negative"], 1)

    def test_delete_missing_knowledge_source_files_only_removes_missing(self):
        database.init_db()
        source = database.upsert_knowledge_source("Local", "local_folder", "knowledge", enabled=True)
        database.upsert_knowledge_source_file(
            source["id"],
            document_id="missing-doc",
            path="missing.md",
            content_hash=None,
            file_size=None,
            modified_at=None,
            status="missing",
        )
        database.upsert_knowledge_source_file(
            source["id"],
            document_id="indexed-doc",
            path="indexed.md",
            content_hash="abc",
            file_size=3,
            modified_at="now",
            status="indexed",
        )

        deleted_count = database.delete_missing_knowledge_source_files()
        files = database.list_knowledge_source_files(source["id"])

        self.assertEqual(deleted_count, 1)
        self.assertEqual([file["path"] for file in files], ["indexed.md"])


class KnowledgeAuditPayloadTests(unittest.TestCase):
    def test_build_knowledge_audit_payload_records_scope_and_stats(self):
        payload = database.build_knowledge_audit_payload(
            {
                "role": "user",
                "departments": ["Finance"],
            },
            sources=[{"document_id": "finance.md"}],
            access_stats={"access_filtered_count": 2},
        )

        self.assertEqual(payload["scope"]["role"], "user")
        self.assertEqual(payload["scope"]["departments"], ["Finance"])
        self.assertEqual(payload["access_stats"]["access_filtered_count"], 2)
        self.assertEqual(payload["sources"][0]["document_id"], "finance.md")

    def test_add_and_list_admin_audit_events(self):
        with patched_postgres_database():
            user = database.authenticate_user("admin", "password")
            event_id = database.add_admin_audit_event(
                user,
                "department.create",
                "department",
                target_id=7,
                details={"name": "Finance"},
            )

            events = database.list_admin_audit_events()
            event_count = database.count_admin_audit_events()

        self.assertEqual(event_count, 1)
        self.assertEqual(events[0]["id"], event_id)
        self.assertEqual(events[0]["username"], "admin")
        self.assertEqual(events[0]["action"], "department.create")
        self.assertEqual(events[0]["target_type"], "department")
        self.assertEqual(events[0]["target_id"], "7")
        self.assertEqual(events[0]["details"]["name"], "Finance")


if __name__ == "__main__":
    unittest.main()
