# -*- coding: utf-8 -*-

import argparse
import csv
import json
import os
import socket
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCS_DIR = PROJECT_ROOT / "rag_eval" / "sample_docs"
DEFAULT_QUESTIONS_FILE = PROJECT_ROOT / "rag_eval" / "questions.json"
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "rag_eval" / "reports"


def read_env_file(path):
    values = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")

    return values


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class ApiClient:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/") + "/"
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def request_json(self, method, path, payload=None, headers=None):
        body = None
        request_headers = dict(headers or {})
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            request_headers["Content-Type"] = "application/json"

        request = Request(
            urljoin(self.base_url, path.lstrip("/")),
            data=body,
            headers=request_headers,
            method=method,
        )

        try:
            with self.opener.open(request, timeout=120) as response:
                content = response.read().decode("utf-8")
                return response.status, json.loads(content) if content else {}
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} failed with {error.code}: {detail}") from error
        except (ConnectionRefusedError, TimeoutError, socket.timeout, URLError) as error:
            raise RuntimeError(format_connection_error(method, path, self.base_url, error)) from error

    def login(self, username, password):
        return self.request_json(
            "POST",
            "/login",
            {"username": username, "password": password},
        )

    def upload_file(self, path, notes=None):
        boundary = "----rag-eval-boundary-7MA4YWxkTrZu0gW"
        body = build_multipart_body(boundary, path, notes)
        request = Request(
            urljoin(self.base_url, "knowledge/upload"),
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )

        try:
            with self.opener.open(request, timeout=180) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"upload {path} failed with {error.code}: {detail}") from error
        except (ConnectionRefusedError, TimeoutError, socket.timeout, URLError) as error:
            raise RuntimeError(format_connection_error("POST", "/knowledge/upload", self.base_url, error)) from error

    def search(self, query, top_k, min_score):
        return self.request_json(
            "POST",
            "/knowledge/search",
            {"query": query, "top_k": top_k, "min_score": min_score},
        )

    def chat(self, message, conversation_id=None):
        payload = {"message": message}
        if conversation_id is not None:
            payload["conversation_id"] = conversation_id
        return self.request_json("POST", "/chat", payload)


def format_connection_error(method, path, base_url, error):
    return (
        f"{method} {path} failed because the backend is not reachable at {base_url}\n"
        "Start the backend first, for example:\n"
        "  cd backend\n"
        "  ..\\.venv\\Scripts\\python.exe -m uvicorn main:app --reload --host 0.0.0.0 --port 8000\n"
        f"Original error: {error}"
    )


def build_multipart_body(boundary, file_path, notes=None):
    lines = []
    if notes:
        lines.extend([
            f"--{boundary}",
            'Content-Disposition: form-data; name="notes"',
            "",
            notes,
        ])

    file_bytes = file_path.read_bytes()
    lines.extend([
        f"--{boundary}",
        f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"',
        "Content-Type: text/markdown",
        "",
    ])
    prefix = "\r\n".join(lines).encode("utf-8") + b"\r\n"
    suffix = f"\r\n--{boundary}--\r\n".encode("utf-8")
    return prefix + file_bytes + suffix


def source_doc_name(document_id):
    if "__" in document_id:
        return document_id.rsplit("__", 1)[-1]
    return document_id


def format_sources(sources):
    if not sources:
        return ""

    return " | ".join(
        (
            f"{source.get('label') or f'R{index}'}:"
            f"{source.get('document_id', '')}"
            f"#chunk{source.get('chunk_index', '')}"
            f" score={source.get('score', 0):.3f}"
        )
        for index, source in enumerate(sources, start=1)
    )


def expected_hit(expected_docs, sources):
    if not expected_docs:
        return len(sources) == 0

    actual_names = {source_doc_name(source.get("document_id", "")) for source in sources}
    return any(expected_doc in actual_names for expected_doc in expected_docs)


def answer_has_citation(answer):
    return "[K" in answer


def upload_docs(client, docs_dir):
    uploaded = []
    for path in sorted(docs_dir.glob("*")):
        if path.suffix.lower() not in {".md", ".txt"}:
            continue

        _, data = client.upload_file(path, notes="rag_eval sample document")
        uploaded.append(data)
        print(f"uploaded {path.name}: {data.get('chunk_count')} chunk(s)", flush=True)

    return uploaded


def run_questions(client, questions, top_k, min_score, skip_chat):
    rows = []
    for index, question in enumerate(questions, start=1):
        question_text = question["question"]
        print(f"[{index}/{len(questions)}] {question_text}", flush=True)

        _, search_data = client.search(question_text, top_k=top_k, min_score=min_score)
        search_sources = search_data.get("results", [])

        answer = ""
        chat_sources = []
        conversation_id = None
        if not skip_chat:
            _, chat_data = client.chat(question_text)
            answer = chat_data.get("answer", "")
            chat_sources = chat_data.get("sources", [])
            conversation_id = chat_data.get("conversation_id")

        sources_for_score = chat_sources if chat_sources else search_sources
        top_source = sources_for_score[0] if sources_for_score else {}
        expected_docs = question.get("expected_docs", [])
        matched_expected = expected_hit(expected_docs, sources_for_score)
        row = {
            "id": question.get("id", ""),
            "category": question.get("category", ""),
            "question": question_text,
            "expected_docs": ", ".join(expected_docs),
            "expected_hit": matched_expected,
            "unexpected_sources": not expected_docs and bool(sources_for_score),
            "top_document": top_source.get("document_id", ""),
            "top_score": top_source.get("score", ""),
            "source_count": len(sources_for_score),
            "answer_has_citation": answer_has_citation(answer),
            "conversation_id": conversation_id if conversation_id is not None else "",
            "sources": format_sources(sources_for_score),
            "answer": answer,
        }
        rows.append(row)

    return rows


def write_reports(rows, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    json_path = output_dir / f"rag_eval_{stamp}.json"
    csv_path = output_dir / f"rag_eval_{stamp}.csv"
    md_path = output_dir / f"rag_eval_{stamp}.md"

    dump_json(json_path, rows)

    fieldnames = [
        "id",
        "category",
        "question",
        "expected_docs",
        "expected_hit",
        "unexpected_sources",
        "top_document",
        "top_score",
        "source_count",
        "answer_has_citation",
        "conversation_id",
        "sources",
        "answer",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    total = len(rows)
    expected_hits = sum(1 for row in rows if row["expected_hit"])
    unknown_rows = [row for row in rows if not row["expected_docs"]]
    unexpected_sources = sum(1 for row in unknown_rows if row["unexpected_sources"])
    lines = [
        "# RAG Evaluation Report",
        "",
        f"- Total questions: {total}",
        f"- Expected source matched: {expected_hits}/{total}",
        f"- Unknown questions with unexpected sources: {unexpected_sources}/{len(unknown_rows)}",
        "",
        "| ID | Category | Expected Hit | Unexpected Sources | Top Document | Top Score | Sources |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {id} | {category} | {expected_hit} | {unexpected_sources} | {top_document} | {top_score} | {sources} |".format(
                **{key: str(value).replace("|", "\\|") for key, value in row.items()}
            )
        )

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, csv_path, md_path


def parse_args():
    parser = argparse.ArgumentParser(description="Upload docs and run a small RAG evaluation set.")
    parser.add_argument("--base-url", default=os.environ.get("RAG_EVAL_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--username", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--min-score", type=float, default=0.3)
    parser.add_argument("--skip-upload", action="store_true")
    parser.add_argument("--skip-chat", action="store_true", help="Only run /knowledge/search, not /chat.")
    return parser.parse_args()


def main():
    args = parse_args()
    env = read_env_file(PROJECT_ROOT / ".env")
    username = args.username or os.environ.get("APP_USERNAME") or env.get("APP_USERNAME") or "admin"
    password = args.password or os.environ.get("APP_PASSWORD") or env.get("APP_PASSWORD")
    if not password:
        raise SystemExit("Missing password. Pass --password or set APP_PASSWORD in .env.")

    client = ApiClient(args.base_url)
    client.login(username, password)
    print(f"logged in as {username}", flush=True)

    if not args.skip_upload:
        upload_docs(client, args.docs_dir)

    questions = load_json(args.questions)
    rows = run_questions(client, questions, args.top_k, args.min_score, args.skip_chat)
    json_path, csv_path, md_path = write_reports(rows, args.output_dir)
    print(f"wrote {json_path}", flush=True)
    print(f"wrote {csv_path}", flush=True)
    print(f"wrote {md_path}", flush=True)


if __name__ == "__main__":
    main()
