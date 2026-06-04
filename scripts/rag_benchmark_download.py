# -*- coding: utf-8 -*-

import argparse
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "rag_eval" / "benchmark_inputs" / "ragbench_emanual_sample.jsonl"
DATASETS_SERVER = "https://datasets-server.huggingface.co"


def fetch_first_rows(dataset, config, split, timeout=60):
    query = urlencode({
        "dataset": dataset,
        "config": config,
        "split": split,
    })
    url = f"{DATASETS_SERVER}/first-rows?{query}"
    try:
        with urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Hugging Face request failed with {error.code}: {detail}") from error
    except URLError as error:
        raise RuntimeError(f"Hugging Face request failed: {error}") from error


def normalize_ragbench_row(row_item):
    row = row_item["row"]
    sample_id = row.get("id") or f"row_{row_item.get('row_idx', 0)}"
    documents = row.get("documents") or []
    normalized_docs = []
    for index, document in enumerate(documents, start=1):
        normalized_docs.append({
            "title": f"{sample_id}_doc_{index}",
            "text": document,
        })

    return {
        "id": sample_id,
        "question": row.get("question", ""),
        "answer": row.get("response") or row.get("answer") or "",
        "documents": normalized_docs,
        "metadata": {
            "source_dataset": "ragbench",
            "row_idx": row_item.get("row_idx"),
        },
    }


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_args():
    parser = argparse.ArgumentParser(description="Download a small RAGBench sample from Hugging Face.")
    parser.add_argument("--dataset", default="galileo-ai/ragbench")
    parser.add_argument("--config", default="emanual")
    parser.add_argument("--split", default="test")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main():
    args = parse_args()
    data = fetch_first_rows(args.dataset, args.config, args.split)
    rows = [normalize_ragbench_row(row_item) for row_item in data.get("rows", [])[:args.limit]]
    rows = [row for row in rows if row["question"] and row["documents"]]
    write_jsonl(args.output, rows)
    print(f"downloaded {len(rows)} sample(s)")
    print(f"output: {args.output}")
    print("next:")
    print(f"  .\\.venv\\Scripts\\python.exe scripts\\rag_benchmark_prepare.py --input {args.output} --output-dir rag_eval\\generated\\ragbench_{args.config}")


if __name__ == "__main__":
    main()

