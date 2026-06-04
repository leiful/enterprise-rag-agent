# -*- coding: utf-8 -*-

import argparse
import json
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "rag_eval" / "benchmark_inputs" / "tiny_public_style.jsonl"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "rag_eval" / "generated"


def load_jsonl(path, limit=None):
    rows = []
    with path.open("r", encoding="utf-8") as input_file:
        for line_number, raw_line in enumerate(input_file, start=1):
            line = raw_line.strip()
            if not line:
                continue

            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number} is not valid JSON: {error}") from error

            if limit and len(rows) >= limit:
                break

    return rows


def safe_name(value, fallback):
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
    clean = clean.strip("._-")
    return clean[:80] or fallback


def as_text(value):
    if value is None:
        return ""

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, list):
        return "\n\n".join(as_text(item) for item in value if as_text(item)).strip()

    if isinstance(value, dict):
        parts = []
        for key in ("title", "heading", "text", "contents", "content", "body", "passage"):
            text = as_text(value.get(key))
            if text:
                parts.append(text)
        return "\n\n".join(parts).strip()

    return str(value).strip()


def get_first(record, keys, default=None):
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
    return default


def extract_documents(record):
    documents = get_first(
        record,
        ["documents", "docs", "contexts", "context", "passages", "positive_ctxs"],
        [],
    )
    if isinstance(documents, str):
        documents = [{"title": "context", "text": documents}]
    elif isinstance(documents, dict):
        documents = [documents]

    extracted = []
    for index, document in enumerate(documents or [], start=1):
        if isinstance(document, str):
            title = f"doc_{index}"
            text = document
        else:
            title = get_first(document, ["title", "name", "id", "doc_id"], f"doc_{index}")
            text = get_first(
                document,
                ["text", "contents", "content", "body", "passage"],
                "",
            )
            if not text:
                text = as_text(document)

        clean_text = as_text(text)
        if clean_text:
            extracted.append({
                "title": str(title),
                "text": clean_text,
            })

    return extracted


def normalize_record(record, index):
    sample_id = safe_name(get_first(record, ["id", "qid", "question_id"], f"sample_{index:04d}"), f"sample_{index:04d}")
    question = as_text(get_first(record, ["question", "query", "input", "prompt"]))
    answer = as_text(get_first(record, ["answer", "answers", "response", "output", "gold_answer"], ""))
    documents = extract_documents(record)

    if not question:
        raise ValueError(f"sample {sample_id} has no question/query field")

    if not documents:
        raise ValueError(f"sample {sample_id} has no documents/context field")

    return {
        "id": sample_id,
        "question": question,
        "answer": answer,
        "documents": documents,
    }


def write_markdown(path, sample, document):
    content = [
        f"# {document['title']}",
        "",
        f"Benchmark sample id: {sample['id']}",
        "",
        document["text"],
        "",
    ]
    if sample["answer"]:
        content.extend([
            "## Reference Answer",
            "",
            sample["answer"],
            "",
        ])

    path.write_text("\n".join(content), encoding="utf-8")


def prepare_benchmark(input_path, output_dir, limit=None):
    samples = [normalize_record(record, index) for index, record in enumerate(load_jsonl(input_path, limit), start=1)]
    docs_dir = output_dir / "docs"
    questions_path = output_dir / "questions.json"
    docs_dir.mkdir(parents=True, exist_ok=True)

    questions = []
    for sample_index, sample in enumerate(samples, start=1):
        expected_docs = []
        for doc_index, document in enumerate(sample["documents"], start=1):
            file_name = f"{sample_index:04d}_{safe_name(sample['id'], f'sample_{sample_index:04d}')}_{doc_index:02d}_{safe_name(document['title'], 'doc')}.md"
            write_markdown(docs_dir / file_name, sample, document)
            expected_docs.append(file_name)

        questions.append({
            "id": sample["id"],
            "question": sample["question"],
            "expected_docs": expected_docs,
            "category": "public_benchmark",
            "reference_answer": sample["answer"],
        })

    questions_path.write_text(json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8")
    return docs_dir, questions_path, len(samples)


def parse_args():
    parser = argparse.ArgumentParser(description="Convert public RAG benchmark JSONL into local rag_eval docs/questions.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args()


def main():
    args = parse_args()
    docs_dir, questions_path, sample_count = prepare_benchmark(args.input, args.output_dir, args.limit)
    print(f"converted {sample_count} sample(s)")
    print(f"docs: {docs_dir}")
    print(f"questions: {questions_path}")
    print("run:")
    print(f"  .\\.venv\\Scripts\\python.exe scripts\\rag_eval.py --docs-dir {docs_dir} --questions {questions_path}")


if __name__ == "__main__":
    main()

