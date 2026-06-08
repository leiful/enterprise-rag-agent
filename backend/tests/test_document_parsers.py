import tempfile
import unittest
from pathlib import Path

import document_parsers


class DocumentParserSegmentTests(unittest.TestCase):
    def test_markdown_segments_keep_heading_path(self):
        text = "# Policy\n\nIntro\n\n## Reimbursement\n\nReceipt required."

        segments = document_parsers.split_markdown_sections(text)

        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0]["metadata"]["section_path"], "Policy")
        self.assertEqual(segments[1]["metadata"]["section_path"], "Policy > Reimbursement")
        self.assertIn("Receipt required.", segments[1]["text"])

    def test_csv_segments_keep_sheet_header_and_row_number(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "employees.csv"
            path.write_text("Name,Department\nAlice,Finance\nBob,Legal\n", encoding="utf-8")

            segments, error = document_parsers.parse_csv_segments(path)

        self.assertIsNone(error)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0]["metadata"]["sheet_name"], "employees")
        self.assertEqual(segments[0]["metadata"]["row_start"], 2)
        self.assertEqual(segments[0]["metadata"]["table_header"], ["Name", "Department"])
        self.assertIn("Department: Finance", segments[0]["text"])
        self.assertIn("Record: Name: Alice | Department: Finance", segments[0]["text"])

    def test_pdf_without_extractable_text_reports_ocr_need(self):
        class EmptyPage:
            def extract_text(self):
                return ""

        class EmptyReader:
            pages = [EmptyPage()]

        with unittest.mock.patch.dict("sys.modules", {"pypdf": unittest.mock.Mock(PdfReader=lambda _: EmptyReader())}):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "scan.pdf"
                path.write_bytes(b"%PDF-1.4")
                segments, error = document_parsers.parse_pdf_segments(path)

        self.assertEqual(segments, [])
        self.assertIn("requires OCR", error)


if __name__ == "__main__":
    unittest.main()
