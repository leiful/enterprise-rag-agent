# -*- coding: utf-8 -*-

import argparse
import csv
import json
import os
import socket
import sys
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


class LocalApiClient:
    def __init__(self, search_callback, chat_callback=None):
        self.search_callback = search_callback
        self.chat_callback = chat_callback

    def search(self, query, top_k, min_score):
        return 200, self.search_callback(query, top_k, min_score)

    def chat(self, message, conversation_id=None):
        if not self.chat_callback:
            return 200, {"answer": "", "sources": [], "conversation_id": conversation_id}
        return 200, self.chat_callback(message, conversation_id)


def format_connection_error(method, path, base_url, error):
    return (
        f"{method} {path} failed because the backend is not reachable at {base_url}\n"
        "Start the backend first, for example:\n"
        "  cd backend\n"
        "  ..\\.venv\\Scripts\\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000\n"
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


def expected_rank(expected_docs, sources):
    if not expected_docs:
        return None

    for index, source in enumerate(sources, start=1):
        if source_doc_name(source.get("document_id", "")) in expected_docs:
            return index
    return None


def answer_has_citation(answer):
    normalized = str(answer or "")
    return "[K" in normalized or "【K" in normalized


def answer_abstained(answer):
    normalized = (answer or "").lower()
    abstention_phrases = (
        "????",
        "????",
        "????",
        "???",
        "????",
        "????",
        "?????",
        "???",
        "???",
        "???",
        "??",
        "??????",
        "??????",
        "????????",
        "does not contain",
        "does not contain enough",
        "not enough evidence",
        "insufficient evidence",
        "no supported knowledge evidence",
        "cannot answer",
        "unable to answer",
    )
    return any(phrase in normalized for phrase in abstention_phrases)


def normalize_text(value):
    return " ".join(str(value or "").lower().split())


def expected_term_alternatives(term):
    if isinstance(term, list):
        return [str(item) for item in term if str(item).strip()]
    return [item.strip() for item in str(term or "").split("||") if item.strip()]


def expected_term_matched(term, normalized_text):
    return any(
        normalize_text(alternative) in normalized_text
        for alternative in expected_term_alternatives(term)
    )


def expected_terms_score(expected_terms, answer):
    if not expected_terms:
        return None

    normalized_answer = normalize_text(answer)
    if not normalized_answer:
        return 0.0

    hits = sum(1 for term in expected_terms if expected_term_matched(term, normalized_answer))
    return hits / len(expected_terms)


def expected_terms_hit(expected_terms, answer, *, threshold=0.6):
    score = expected_terms_score(expected_terms, answer)
    if score is None:
        return None
    return score >= threshold


def source_text_terms_score(expected_terms, sources):
    if not expected_terms:
        return None

    combined_text = normalize_text(" ".join(source.get("text", "") for source in sources))
    if not combined_text:
        return 0.0

    hits = sum(1 for term in expected_terms if expected_term_matched(term, combined_text))
    return hits / len(expected_terms)


def source_text_terms_hit(expected_terms, sources, *, threshold=0.6):
    score = source_text_terms_score(expected_terms, sources)
    if score is None:
        return None
    return score >= threshold


def format_contexts(sources):
    return [
        {
            "document_id": source.get("document_id", ""),
            "chunk_id": source.get("chunk_id", ""),
            "chunk_index": source.get("chunk_index", ""),
            "score": source.get("score", ""),
            "text": source.get("text", ""),
        }
        for source in sources
    ]


def failure_reasons_for_row(row):
    reasons = []
    if row["expected_docs"] and not row["expected_hit"]:
        reasons.append("expected_source_missed")
    if row["expected_docs"] and row.get("evidence_terms_hit") is False:
        reasons.append("evidence_terms_missing")
    if row["expected_docs"] and row["answer"] and not row["answer_has_citation"]:
        reasons.append("missing_citation")
    if row["answer"] and row["expected_terms_hit"] is False and not row.get("should_abstain"):
        reasons.append("expected_terms_missing")
    if row["unexpected_sources"] and not row.get("should_abstain"):
        reasons.append("unexpected_source_for_unknown")
    if row.get("should_abstain") and row["answer"] and not answer_abstained(row["answer"]):
        reasons.append("unknown_not_abstained")
    return reasons


def upload_docs(client, docs_dir):
    uploaded = []
    for path in sorted(docs_dir.glob("*")):
        if path.suffix.lower() not in {".md", ".txt"}:
            continue

        _, data = client.upload_file(path, notes="rag_eval sample document")
        uploaded.append(data)
        print(f"uploaded {path.name}: {data.get('chunk_count')} chunk(s)", flush=True)

    return uploaded


def run_questions(client, questions, top_k, min_score, skip_chat, skip_search=False):
    rows = []
    for index, question in enumerate(questions, start=1):
        question_text = question["question"]
        print(f"[{index}/{len(questions)}] {question_text}", flush=True)

        search_sources = []
        if not skip_search:
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
        expected_terms = question.get("expected_terms", [])
        matched_expected = expected_hit(expected_docs, sources_for_score)
        rank = expected_rank(expected_docs, sources_for_score)
        expected_terms_matched = expected_terms_hit(expected_terms, answer)
        term_score = expected_terms_score(expected_terms, answer)
        evidence_terms_matched = source_text_terms_hit(expected_terms, sources_for_score)
        evidence_term_score = source_text_terms_score(expected_terms, sources_for_score)
        should_abstain = bool(question.get("should_abstain"))
        row = {
            "id": question.get("id", ""),
            "category": question.get("category", ""),
            "question": question_text,
            "expected_docs": ", ".join(expected_docs),
            "expected_answer": question.get("expected_answer", ""),
            "expected_terms": ", ".join(expected_terms),
            "expected_terms_hit": expected_terms_matched if expected_terms_matched is not None else "",
            "expected_terms_score": f"{term_score:.3f}" if term_score is not None else "",
            "evidence_terms_hit": evidence_terms_matched if evidence_terms_matched is not None else "",
            "evidence_terms_score": f"{evidence_term_score:.3f}" if evidence_term_score is not None else "",
            "should_abstain": should_abstain,
            "expected_hit": matched_expected,
            "expected_rank": rank or "",
            "top1_hit": rank == 1,
            "unexpected_sources": not expected_docs and not should_abstain and bool(sources_for_score),
            "top_document": top_source.get("document_id", ""),
            "top_score": top_source.get("score", ""),
            "source_count": len(sources_for_score),
            "answer_has_citation": answer_has_citation(answer),
            "abstained": answer_abstained(answer),
            "conversation_id": conversation_id if conversation_id is not None else "",
            "sources": format_sources(sources_for_score),
            "contexts": format_contexts(sources_for_score),
            "answer": answer,
        }
        row["failure_reasons"] = failure_reasons_for_row(row)
        row["strict_failure"] = bool(row["failure_reasons"])
        rows.append(row)

    return rows


def summarize_rows(rows):
    total = len(rows)
    answerable_rows = [row for row in rows if row["expected_docs"]]
    expected_hits = sum(1 for row in answerable_rows if row["expected_hit"])
    top1_hits = sum(1 for row in answerable_rows if row["top1_hit"])
    reciprocal_rank_total = sum(
        1 / int(row["expected_rank"])
        for row in answerable_rows
        if row["expected_rank"]
    )
    mrr = reciprocal_rank_total / len(answerable_rows) if answerable_rows else 0.0
    citation_rows = [row for row in rows if row["answer"]]
    citation_rate = (
        sum(1 for row in citation_rows if row["answer_has_citation"]) / len(citation_rows)
        if citation_rows
        else 0.0
    )
    unknown_rows = [row for row in rows if not row["expected_docs"]]
    unexpected_sources = sum(1 for row in unknown_rows if row["unexpected_sources"])
    strict_failures = sum(1 for row in rows if row.get("strict_failure"))
    evidence_rows = [
        row for row in answerable_rows
        if row.get("evidence_terms_hit") != ""
    ]
    evidence_hits = sum(1 for row in evidence_rows if row.get("evidence_terms_hit") is True)
    failure_reasons = {}
    for row in rows:
        for reason in row.get("failure_reasons") or []:
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
    abstention_accuracy = (
        (len(unknown_rows) - unexpected_sources) / len(unknown_rows)
        if unknown_rows
        else 0.0
    )
    return {
        "total": total,
        "answerable_total": len(answerable_rows),
        "expected_hits": expected_hits,
        "recall_at_k": expected_hits / len(answerable_rows) if answerable_rows else 0.0,
        "top1_hits": top1_hits,
        "top1_hit_rate": top1_hits / len(answerable_rows) if answerable_rows else 0.0,
        "mrr": mrr,
        "citation_rate": citation_rate,
        "abstention_accuracy": abstention_accuracy,
        "strict_failures": strict_failures,
        "evidence_hits": evidence_hits,
        "evidence_total": len(evidence_rows),
        "evidence_hit_rate": evidence_hits / len(evidence_rows) if evidence_rows else 0.0,
        "failure_reasons": failure_reasons,
        "unknown_total": len(unknown_rows),
        "unexpected_sources": unexpected_sources,
    }


def write_reports(rows, output_dir, suite_id=None):
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    prefix = f"rag_eval_{suite_id}_" if suite_id else "rag_eval_"
    json_path = output_dir / f"{prefix}{stamp}.json"
    csv_path = output_dir / f"{prefix}{stamp}.csv"
    md_path = output_dir / f"{prefix}{stamp}.md"
    ragas_path = output_dir / f"{prefix}{stamp}.ragas.jsonl"
    deepeval_path = output_dir / f"{prefix}{stamp}.deepeval.json"

    dump_json(json_path, rows)
    with ragas_path.open("w", encoding="utf-8") as output:
        for item in rows_to_ragas_dataset(rows):
            output.write(json.dumps(item, ensure_ascii=False) + "\n")
    dump_json(deepeval_path, rows_to_deepeval_dataset(rows))

    fieldnames = [
        "id",
        "category",
        "question",
        "expected_docs",
        "expected_answer",
        "expected_terms",
        "expected_terms_hit",
        "expected_terms_score",
        "evidence_terms_hit",
        "evidence_terms_score",
        "should_abstain",
        "expected_hit",
        "expected_rank",
        "top1_hit",
        "unexpected_sources",
        "top_document",
        "top_score",
        "source_count",
        "answer_has_citation",
        "abstained",
        "strict_failure",
        "failure_reasons",
        "conversation_id",
        "sources",
        "contexts",
        "answer",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    summary = summarize_rows(rows)
    lines = [
        "# RAG Evaluation Report",
        "",
        f"- Total questions: {summary['total']}",
        f"- Recall@K: {summary['expected_hits']}/{summary['answerable_total']}",
        f"- Top-1 hit rate: {summary['top1_hits']}/{summary['answerable_total']}",
        f"- MRR: {summary['mrr']:.3f}",
        f"- Citation rate: {summary['citation_rate']:.3f}",
        f"- Abstention accuracy: {summary['abstention_accuracy']:.3f}",
        f"- Evidence hit rate: {summary['evidence_hit_rate']:.3f}",
        f"- Strict failures: {summary['strict_failures']}/{summary['total']}",
        f"- Failure reasons: {json.dumps(summary['failure_reasons'], ensure_ascii=False, sort_keys=True)}",
        f"- Unknown questions with unexpected sources: {summary['unexpected_sources']}/{summary['unknown_total']}",
        "",
        "| ID | Category | Expected Hit | Rank | Top-1 | Unexpected Sources | Top Document | Top Score | Sources |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {id} | {category} | {expected_hit} | {expected_rank} | {top1_hit} | {unexpected_sources} | {top_document} | {top_score} | {sources} |".format(
                **{key: str(value).replace("|", "\\|") for key, value in row.items()}
            )
        )

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, csv_path, md_path, summary


def rows_to_ragas_dataset(rows):
    return [
        {
            "question": row["question"],
            "answer": row.get("answer", ""),
            "contexts": [
                context.get("text", "")
                for context in row.get("contexts", [])
                if context.get("text")
            ],
            "ground_truth": row.get("expected_answer", ""),
            "metadata": {
                "id": row.get("id", ""),
                "category": row.get("category", ""),
                "expected_docs": row.get("expected_docs", ""),
            },
        }
        for row in rows
    ]


def rows_to_deepeval_dataset(rows):
    return [
        {
            "input": row["question"],
            "actual_output": row.get("answer", ""),
            "expected_output": row.get("expected_answer", ""),
            "retrieval_context": [
                context.get("text", "")
                for context in row.get("contexts", [])
                if context.get("text")
            ],
            "metadata": {
                "id": row.get("id", ""),
                "category": row.get("category", ""),
                "expected_docs": row.get("expected_docs", ""),
                "expected_terms": row.get("expected_terms", ""),
            },
        }
        for row in rows
    ]


def evaluate_quality_gate(summary, args):
    failures = []
    checks = [
        ("recall_at_k", summary["recall_at_k"], args.min_recall),
        ("top1_hit_rate", summary["top1_hit_rate"], args.min_top1),
        ("mrr", summary["mrr"], args.min_mrr),
        ("citation_rate", summary["citation_rate"], args.min_citation_rate),
        ("abstention_accuracy", summary["abstention_accuracy"], args.min_abstention_accuracy),
    ]
    for name, actual, expected in checks:
        if actual < expected:
            failures.append(f"{name} {actual:.3f} < {expected:.3f}")

    if summary["strict_failures"] > args.max_strict_failures:
        failures.append(
            f"strict_failures {summary['strict_failures']} > {args.max_strict_failures}"
        )
    if summary["unexpected_sources"] > args.max_unexpected_sources:
        failures.append(
            f"unexpected_sources {summary['unexpected_sources']} > {args.max_unexpected_sources}"
        )
    return failures


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
    parser.add_argument("--skip-search", action="store_true", help="Only use /chat sources; avoids duplicate retrieval during answer tests.")
    parser.add_argument("--fail-on-threshold", action="store_true", help="Exit with status 1 when quality gates fail.")
    parser.add_argument("--min-recall", type=float, default=1.0)
    parser.add_argument("--min-top1", type=float, default=0.8)
    parser.add_argument("--min-mrr", type=float, default=0.9)
    parser.add_argument("--min-citation-rate", type=float, default=0.9)
    parser.add_argument("--min-abstention-accuracy", type=float, default=1.0)
    parser.add_argument("--max-strict-failures", type=int, default=0)
    parser.add_argument("--max-unexpected-sources", type=int, default=0)
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
    rows = run_questions(client, questions, args.top_k, args.min_score, args.skip_chat, skip_search=args.skip_search)
    json_path, csv_path, md_path, summary = write_reports(rows, args.output_dir)
    print(f"wrote {json_path}", flush=True)
    print(f"wrote {csv_path}", flush=True)
    print(f"wrote {md_path}", flush=True)
    print(f"wrote {json_path.with_suffix('.ragas.jsonl')}", flush=True)
    print(f"wrote {json_path.with_suffix('.deepeval.json')}", flush=True)
    print(
        "summary: "
        f"recall={summary['recall_at_k']:.3f}, "
        f"top1={summary['top1_hit_rate']:.3f}, "
        f"mrr={summary['mrr']:.3f}, "
        f"citation={summary['citation_rate']:.3f}, "
        f"abstention={summary['abstention_accuracy']:.3f}, "
        f"strict_failures={summary['strict_failures']}, "
        f"unexpected_sources={summary['unexpected_sources']}",
        flush=True,
    )

    gate_failures = evaluate_quality_gate(summary, args)
    if gate_failures:
        print("quality gate failures:", flush=True)
        for failure in gate_failures:
            print(f"- {failure}", flush=True)
        if args.fail_on_threshold:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
