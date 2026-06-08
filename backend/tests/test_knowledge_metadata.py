import unittest

import knowledge


class KnowledgeMetadataValidationTests(unittest.TestCase):
    def test_valid_metadata_is_normalized(self):
        metadata, error = knowledge.validate_document_metadata(
            {
                "department": " Finance ",
                "sensitivity": "CONFIDENTIAL",
                "status": "Active",
                "doc_type": "Policy",
                "canonical_id": " POLICY-001 ",
                "version": " 2.0 ",
                "effective_date": "2025-01-01",
                "expiry_date": "2025-12-31",
            }
        )

        self.assertIsNone(error)
        self.assertEqual(metadata["department"], "Finance")
        self.assertEqual(metadata["sensitivity"], "confidential")
        self.assertEqual(metadata["status"], "active")
        self.assertEqual(metadata["doc_type"], "policy")
        self.assertEqual(metadata["canonical_id"], "POLICY-001")
        self.assertTrue(metadata["effective_date"].startswith("2025-01-01T"))
        self.assertTrue(metadata["expiry_date"].startswith("2025-12-31T"))

    def test_unknown_metadata_key_is_rejected(self):
        metadata, error = knowledge.validate_document_metadata({"unknown": "value"})

        self.assertIsNone(metadata)
        self.assertEqual(error, "unsupported metadata keys: unknown")

    def test_invalid_enum_value_is_rejected(self):
        metadata, error = knowledge.validate_document_metadata({"sensitivity": "secret"})

        self.assertIsNone(metadata)
        self.assertIn("metadata.sensitivity must be one of", error)

    def test_invalid_date_is_rejected(self):
        metadata, error = knowledge.validate_document_metadata({"effective_date": "tomorrow"})

        self.assertIsNone(metadata)
        self.assertEqual(error, "metadata.effective_date must be an ISO date or datetime")

    def test_expiry_before_effective_date_is_rejected(self):
        metadata, error = knowledge.validate_document_metadata(
            {
                "effective_date": "2025-12-31",
                "expiry_date": "2025-01-01",
            }
        )

        self.assertIsNone(metadata)
        self.assertEqual(error, "metadata.expiry_date must not be earlier than metadata.effective_date")

    def test_system_metadata_keys_cannot_be_overridden_by_user_metadata(self):
        metadata, error = knowledge.validate_document_metadata(
            {
                "file_name": "fake.md",
                "indexed_at": "2000-01-01",
                "owner": "Ops",
            }
        )

        self.assertIsNone(error)
        self.assertEqual(metadata, {"owner": "Ops"})


if __name__ == "__main__":
    unittest.main()
