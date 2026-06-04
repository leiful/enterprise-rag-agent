# Knowledge Base Workflow

The system supports knowledge-base file upload.

Users can upload Markdown or text files. After upload, the backend saves the file, reads the text, splits the text into chunks, creates embeddings for the chunks, and stores the chunk records in SQLite.

Each knowledge document has metadata such as the document id, notes, and update time. Each chunk stores the document id, chunk index, chunk text, embedding JSON, and content hash.

When the user asks a question, the backend searches the indexed chunks and returns source information. Each source contains a label, document id, chunk id, chunk index, score, and original text snippet.

When a knowledge document is deleted, the system deletes both the document metadata and all chunks that belong to the document.

The current upload workflow does not include OCR. Text inside images is not automatically recognized. OCR would require an additional engine such as Tesseract or a cloud OCR service.

