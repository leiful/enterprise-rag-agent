# -*- coding: utf-8 -*-

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import database  # noqa: E402


def parse_timestamp(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z").astimezone(timezone.utc).isoformat()


def infer_scope(record, request_paths):
    request_id = record.get("request_id")
    path = request_paths.get(request_id)
    if path == "/admin/rag/eval/run":
        return "evaluation"
    if path in {"/chat", "/chat/stream"}:
        return "chat"
    if path == "/knowledge/search":
        return "knowledge_search"
    if path and path.startswith("/knowledge"):
        return "indexing"
    return "other"


def add_event(row):
    metadata = dict(row.pop("metadata", {}) or {})
    created_at = row.pop("created_at")
    usage_scope = metadata.get("scope", "other")
    with database.connect() as connection:
        connection.execute(
            """
            INSERT INTO model_usage_events (
                provider, model, operation, request_id, usage_scope,
                input_tokens_estimate, output_tokens_estimate,
                input_chars, output_chars, document_count,
                metadata_json, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                row["provider"],
                row["model"],
                row["operation"],
                row.get("request_id"),
                usage_scope,
                int(row.get("input_tokens_estimate") or 0),
                int(row.get("output_tokens_estimate") or 0),
                int(row.get("input_chars") or 0),
                int(row.get("output_chars") or 0),
                int(row.get("document_count") or 0),
                json.dumps(metadata, ensure_ascii=False),
                created_at,
            ),
        )


def build_backfill_events(records, target_date):
    request_paths = {
        record.get("request_id"): record.get("path")
        for record in records
        if record.get("event") == "http_request_completed" and record.get("request_id")
    }

    events = []
    seen_rerank_completed = set()
    for record in records:
        timestamp = record.get("timestamp", "")
        if not timestamp.startswith(target_date):
            continue

        message = record.get("message", "")
        request_id = record.get("request_id")
        created_at = parse_timestamp(timestamp)
        scope = infer_scope(record, request_paths)

        if "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings" in message:
            events.append({
                "provider": "dashscope",
                "model": "text-embedding-v4",
                "operation": "embedding",
                "request_id": request_id,
                "input_tokens_estimate": 128,
                "input_chars": 512,
                "document_count": 1,
                "metadata": {"scope": scope, "source": "log_backfill"},
                "created_at": created_at,
            })
            continue

        if "https://api.deepseek.com/chat/completions" in message:
            events.append({
                "provider": "deepseek",
                "model": "deepseek-v4-flash",
                "operation": "chat",
                "request_id": request_id,
                "input_tokens_estimate": 1000,
                "output_tokens_estimate": 250,
                "input_chars": 4000,
                "output_chars": 1000,
                "document_count": 0,
                "metadata": {"scope": scope, "source": "log_backfill"},
                "created_at": created_at,
            })
            continue

        if record.get("event") == "dashscope_rerank_completed":
            key = (request_id, timestamp, record.get("candidate_count"), record.get("top_k"))
            seen_rerank_completed.add(key)
            document_chars = int(record.get("document_chars") or 0)
            query_chars = int(record.get("query_chars") or 0)
            input_chars = document_chars + query_chars
            events.append({
                "provider": "dashscope",
                "model": record.get("model") or "gte-rerank-v2",
                "operation": "rerank",
                "request_id": request_id,
                "input_tokens_estimate": max(1, round(input_chars / 4)),
                "input_chars": input_chars,
                "document_count": int(record.get("candidate_count") or 0),
                "metadata": {
                    "scope": scope,
                    "source": "log_backfill",
                    "top_k": record.get("top_k"),
                    "original_candidate_count": record.get("original_candidate_count"),
                },
                "created_at": created_at,
            })
            continue

        if record.get("event") == "retrieval_completed" and record.get("rerank_enabled"):
            candidate_count = int(record.get("candidate_count") or 0)
            events.append({
                "provider": "dashscope",
                "model": "gte-rerank-v2",
                "operation": "rerank",
                "request_id": request_id,
                "input_tokens_estimate": candidate_count * 125,
                "input_chars": candidate_count * 500,
                "document_count": candidate_count,
                "metadata": {
                    "scope": scope,
                    "source": "log_backfill_retrieval_proxy",
                    "top_k": record.get("top_k"),
                    "recall_k": record.get("recall_k"),
                },
                "created_at": created_at,
            })

    return events


def main():
    parser = argparse.ArgumentParser(description="Backfill model usage from JSON logs.")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--log", type=Path, default=PROJECT_ROOT / "logs" / "app.jsonl")
    args = parser.parse_args()

    database.ensure_model_usage_schema()
    records = []
    for line in args.log.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    events = build_backfill_events(records, args.date)
    for event in events:
        add_event(event)

    print(f"backfilled {len(events)} model usage event(s) for {args.date}")


if __name__ == "__main__":
    main()
