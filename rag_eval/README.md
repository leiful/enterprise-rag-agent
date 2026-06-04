# RAG Evaluation

This folder contains a small local RAG evaluation pack.

- `sample_docs/` contains Markdown documents that can be uploaded to the knowledge base.
- `questions.json` contains evaluation questions and expected source documents.
- `benchmark_inputs/` contains tiny JSONL examples shaped like public RAG benchmark samples.
- `generated/` is the default output folder for converted public benchmark samples.
- `reports/` is the default output folder for generated evaluation reports.

The first goal is not to prove a perfect score. The goal is to observe retrieval behavior:

- Which document appears as K1/K2/K3?
- What score does each source receive?
- Does the answer cite relevant snippets?
- Does the assistant correctly say that evidence is missing?
- Do keyword-similar distractor questions pull unrelated chunks?

## Public Benchmark Conversion

Use `scripts/rag_benchmark_prepare.py` to convert a small public benchmark sample
into local Markdown documents and a matching questions file.

Input JSONL records can use fields such as:

```json
{
  "id": "sample_001",
  "question": "What should the assistant do with unrelated snippets?",
  "answer": "It should say the knowledge base lacks enough evidence.",
  "documents": [
    {"title": "Grounding Policy", "text": "RAG answers must cite only supported claims."}
  ]
}
```

Convert the tiny built-in example:

```powershell
.\.venv\Scripts\python.exe scripts\rag_benchmark_prepare.py
```

Then run it through the same evaluator:

```powershell
.\.venv\Scripts\python.exe scripts\rag_eval.py --docs-dir rag_eval\generated\docs --questions rag_eval\generated\questions.json
```

For real public datasets such as RAGBench, HotpotQA, or BEIR, first export a
small JSONL sample with `question` and `documents`, then pass it with `--input`.

To download a small RAGBench sample directly from Hugging Face:

```powershell
.\.venv\Scripts\python.exe scripts\rag_benchmark_download.py --config emanual --split test --limit 5
.\.venv\Scripts\python.exe scripts\rag_benchmark_prepare.py --input rag_eval\benchmark_inputs\ragbench_emanual_sample.jsonl --output-dir rag_eval\generated\ragbench_emanual
.\.venv\Scripts\python.exe scripts\rag_eval.py --docs-dir rag_eval\generated\ragbench_emanual\docs --questions rag_eval\generated\ragbench_emanual\questions.json
```
