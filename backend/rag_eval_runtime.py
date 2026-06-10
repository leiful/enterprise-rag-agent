# -*- coding: utf-8 -*-

import json
from datetime import datetime, timezone
from pathlib import Path


def build_default_rag_eval_suites(project_root):
    return {
        "core": {
            "id": "core",
            "name": "Core Regression",
            "description": "20 local questions for retrieval, citations, distractors, and no-evidence behavior.",
            "docs_dir": project_root / "rag_eval" / "sample_docs",
            "questions": project_root / "rag_eval" / "questions.json",
            "top_k": 3,
            "min_score": 0.3,
        },
        "acceptance": {
            "id": "acceptance",
            "name": "Acceptance",
            "description": "12 practical acceptance questions for human-facing answer quality.",
            "docs_dir": project_root / "rag_eval" / "sample_docs",
            "questions": project_root / "rag_eval" / "manual_questions.json",
            "top_k": 5,
            "min_score": 0.25,
        },
        "ragbench": {
            "id": "ragbench",
            "name": "RAGBench Sample",
            "description": "5 converted public-benchmark-style eManual questions.",
            "docs_dir": project_root / "rag_eval" / "generated" / "ragbench_emanual" / "docs",
            "questions": project_root / "rag_eval" / "generated" / "ragbench_emanual" / "questions.json",
            "top_k": 3,
            "min_score": 0.3,
        },
        "uploaded_pdfs": {
            "id": "uploaded_pdfs",
            "name": "Uploaded PDF Baseline",
            "description": "37 questions for the uploaded employee handbook, COSENTYX label, and microwave manual.",
            "docs_dir": project_root / "knowledge_files",
            "questions": project_root / "rag_eval" / "uploaded_pdf_questions.json",
            "top_k": 10,
            "min_score": 0.1,
            "skip_upload": True,
        },
    }


def answer_abstained(answer):
    normalized = (answer or "").lower()
    abstention_phrases = (
        "没有足够",
        "没有找到",
        "无法找到",
        "无法从",
        "无法根据",
        "不能根据",
        "不足以回答",
        "不包含",
        "未包含",
        "未提及",
        "缺乏",
        "没有相关证据",
        "知识库中没有",
        "知识库材料中没有",
        "does not contain",
        "does not contain enough",
        "not enough evidence",
        "insufficient evidence",
        "no supported knowledge evidence",
        "cannot answer",
        "unable to answer",
    )
    return any(phrase in normalized for phrase in abstention_phrases)


def answer_has_citation(answer):
    normalized = str(answer or "")
    return "[K" in normalized or "【K" in normalized


def normalize_eval_text(value):
    return " ".join(str(value or "").lower().split())


def eval_term_alternatives(term):
    if isinstance(term, list):
        return [str(item) for item in term if str(item).strip()]
    return [item.strip() for item in str(term or "").split("||") if item.strip()]


def eval_term_matched(term, normalized_text):
    return any(
        normalize_eval_text(alternative) in normalized_text
        for alternative in eval_term_alternatives(term)
    )


def eval_expected_terms(value):
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def eval_evidence_terms_score(row):
    terms = eval_expected_terms(row.get("expected_terms"))
    if not terms:
        return None
    contexts = row.get("contexts") or []
    combined = normalize_eval_text(" ".join(str(context.get("text", "")) for context in contexts))
    if not combined:
        return 0.0
    hits = sum(1 for term in terms if eval_term_matched(term, combined))
    return hits / len(terms)


def eval_answer_terms_score(row):
    terms = eval_expected_terms(row.get("expected_terms"))
    if not terms:
        return None
    combined = normalize_eval_text(row.get("answer", ""))
    if not combined:
        return 0.0
    hits = sum(1 for term in terms if eval_term_matched(term, combined))
    return hits / len(terms)


def rag_eval_suite_list(suites):
    result = []
    for suite in suites.values():
        question_count = 0
        if suite["questions"].exists():
            try:
                question_count = len(json.loads(suite["questions"].read_text(encoding="utf-8")))
            except Exception:
                question_count = 0
        if question_count <= 0:
            continue
        result.append({
            "id": suite["id"],
            "name": suite["name"],
            "description": suite["description"],
            "question_count": question_count,
        })
    return result


def index_rag_eval_docs(docs_dir, *, project_root, knowledge_module):
    indexed = []
    for path in sorted(docs_dir.glob("*")):
        if path.suffix.lower() not in {".md", ".txt"}:
            continue
        relative_path = str(path.relative_to(project_root))
        result, error = knowledge_module.index_file(
            relative_path,
            document_id=path.name,
            notes="rag_eval sample document",
            force_reindex=True,
            use_original_name=True,
        )
        if error:
            raise RuntimeError(f"Failed to index {path.name}: {error}")
        indexed.append(result)
    return indexed


def run_rag_eval_suite(
    suite_id,
    *,
    suites,
    project_root,
    rag_eval_script,
    search_callback,
    chat_callback,
    index_docs_callback,
    skip_chat=False,
    skip_upload=False,
    skip_search=False,
):
    suite = suites.get(suite_id)
    if not suite:
        raise ValueError(f"Unknown evaluation suite: {suite_id}")
    if not suite["questions"].exists():
        raise FileNotFoundError(f"Questions file not found: {suite['questions']}")
    if not suite["docs_dir"].exists():
        raise FileNotFoundError(f"Docs directory not found: {suite['docs_dir']}")

    if not skip_upload and not suite.get("skip_upload"):
        index_docs_callback(suite["docs_dir"])

    questions = rag_eval_script.load_json(suite["questions"])
    rows = rag_eval_script.run_questions(
        rag_eval_script.LocalApiClient(
            search_callback=search_callback,
            chat_callback=None if skip_chat else chat_callback,
        ),
        questions,
        suite["top_k"],
        suite["min_score"],
        skip_chat,
        skip_search=skip_search,
    )
    json_path, csv_path, md_path, summary = rag_eval_script.write_reports(
        rows,
        project_root / "rag_eval" / "reports",
        suite_id=suite["id"],
    )
    return {
        "suite": {
            "id": suite["id"],
            "name": suite["name"],
            "question_count": len(questions),
        },
        "report": {
            "name": json_path.name,
            "path": str(json_path),
            "csv_path": str(csv_path),
            "md_path": str(md_path),
        },
        "summary": summary,
    }


def latest_rag_eval_report(project_root):
    reports_dir = project_root / "rag_eval" / "reports"
    known_suite_ids = set(build_default_rag_eval_suites(project_root))
    report_paths = sorted(
        {
            *(
                path
                for path in reports_dir.glob("rag_eval_*.json")
                if not path.name.endswith(".deepeval.json")
                and report_name_matches_known_suite(path.name, known_suite_ids)
            ),
            *reports_dir.glob("manual_eval_*.json"),
        },
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not report_paths:
        return {"available": False, "report": None, "summary": {}, "rows": []}

    report_path = report_paths[0]
    report_stem = report_path.with_suffix("")
    try:
        report_data = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as error:
        return {
            "available": False,
            "report": {"path": str(report_path), "error": str(error)},
            "summary": {},
            "rows": [],
        }

    rows, manual_summary = normalize_report_rows(report_data)
    apply_latest_question_terms(project_root, report_path, rows)
    enrich_report_rows(rows)
    return build_report_response(report_path, report_stem, rows, manual_summary)


def report_name_matches_known_suite(name, known_suite_ids):
    if not name.startswith("rag_eval_") or name.endswith(".deepeval.json"):
        return False
    suffix = name.removeprefix("rag_eval_")
    if suffix[:8].isdigit():
        return True
    return any(suffix.startswith(f"{suite_id}_") for suite_id in known_suite_ids)


def apply_latest_question_terms(project_root, report_path, rows):
    suites = build_default_rag_eval_suites(project_root)
    suite = None
    for candidate in suites.values():
        if f"_{candidate['id']}_" in report_path.name:
            suite = candidate
            break
    if not suite or not suite["questions"].exists():
        return
    try:
        questions = json.loads(suite["questions"].read_text(encoding="utf-8"))
    except Exception:
        return
    terms_by_id = {
        question.get("id"): question.get("expected_terms")
        for question in questions
        if question.get("id") and question.get("expected_terms")
    }
    for row in rows:
        if row.get("id") in terms_by_id:
            row["expected_terms"] = terms_by_id[row["id"]]


def normalize_report_rows(report_data):
    if isinstance(report_data, dict) and "results" in report_data:
        raw_rows = report_data.get("results") or []
        manual_summary = report_data.get("summary") or {}
        rows = []
        for row in raw_rows:
            normalized = dict(row)
            expected_docs = normalized.get("expected_docs") or []
            top_document = normalized.get("top_document") or normalized.get("k1_document")
            score = normalized.get("score")
            try:
                numeric_score = float(score)
            except (TypeError, ValueError):
                numeric_score = None

            if "expected_hit" not in normalized:
                normalized["expected_hit"] = bool(normalized.get("expected_doc_hit"))
            if "top_document" not in normalized:
                normalized["top_document"] = top_document
            if "top_score" not in normalized:
                normalized["top_score"] = score
            if normalized.get("answer") and answer_abstained(normalized.get("answer")):
                normalized["abstained"] = True
            if "top1_hit" not in normalized:
                normalized["top1_hit"] = bool(top_document and top_document in expected_docs)
            if "unexpected_sources" not in normalized and normalized.get("should_abstain"):
                normalized["unexpected_sources"] = not bool(normalized.get("abstained"))
            if "strict_failure" not in normalized:
                normalized["strict_failure"] = (
                    numeric_score is not None
                    and numeric_score < 7
                    and not (
                        normalized.get("should_abstain")
                        and normalized.get("abstained")
                        and not normalized.get("source_documents")
                    )
                )
            if normalized.get("strict_failure") and not normalized.get("failure_reasons"):
                normalized["failure_reasons"] = ["manual_score_below_7"]
            rows.append(normalized)
        return rows, manual_summary

    return report_data, {}


def enrich_report_rows(rows):
    for row in rows:
        if row.get("answer"):
            row["answer_has_citation"] = answer_has_citation(row.get("answer"))
            row["abstained"] = answer_abstained(row.get("answer"))
            failure_reasons = list(row.get("failure_reasons") or [])
            if row["answer_has_citation"]:
                failure_reasons = [reason for reason in failure_reasons if reason != "missing_citation"]
            if row["abstained"]:
                failure_reasons = [reason for reason in failure_reasons if reason != "unknown_not_abstained"]
                if row.get("should_abstain") or not row.get("expected_docs"):
                    row["unexpected_sources"] = False
            answer_score = eval_answer_terms_score(row)
            if answer_score is not None:
                row["expected_terms_score"] = f"{answer_score:.3f}"
                row["expected_terms_hit"] = answer_score >= 0.6
                failure_reasons = [
                    reason for reason in failure_reasons
                    if reason != "expected_terms_missing"
                ]
                if row.get("expected_docs") and not row["expected_terms_hit"]:
                    failure_reasons.append("expected_terms_missing")
            row["failure_reasons"] = failure_reasons
        if row.get("evidence_terms_hit") == "" or row.get("evidence_terms_hit") is None:
            evidence_score = eval_evidence_terms_score(row)
            if evidence_score is not None:
                row["evidence_terms_score"] = f"{evidence_score:.3f}"
                row["evidence_terms_hit"] = evidence_score >= 0.6
                if row.get("expected_docs") and not row["evidence_terms_hit"]:
                    failure_reasons = list(row.get("failure_reasons") or [])
                    if "evidence_terms_missing" not in failure_reasons:
                        failure_reasons.append("evidence_terms_missing")
                    row["failure_reasons"] = failure_reasons
                    row["strict_failure"] = True
        row["strict_failure"] = bool(row.get("failure_reasons"))


def build_report_response(report_path, report_stem, rows, manual_summary):
    answerable_rows = [row for row in rows if row.get("expected_docs")]
    unknown_rows = [row for row in rows if not row.get("expected_docs")]
    citation_rows = [row for row in rows if row.get("answer")]
    expected_hits = sum(1 for row in answerable_rows if row.get("expected_hit"))
    top1_hits = sum(1 for row in answerable_rows if row.get("top1_hit"))
    evidence_rows = [row for row in answerable_rows if row.get("evidence_terms_hit") != ""]
    evidence_hits = sum(1 for row in evidence_rows if row.get("evidence_terms_hit") is True)
    reciprocal_rank_total = 0
    for row in answerable_rows:
        try:
            if row.get("expected_rank"):
                reciprocal_rank_total += 1 / int(row["expected_rank"])
        except (TypeError, ValueError, ZeroDivisionError):
            continue
    unexpected_sources = sum(1 for row in unknown_rows if row.get("unexpected_sources"))
    abstention_correct = sum(
        1 for row in unknown_rows
        if row.get("abstained") and not row.get("source_documents")
    )
    missing_citations = sum(
        1 for row in answerable_rows
        if row.get("answer") and not row.get("answer_has_citation")
    )
    strict_failures = sum(1 for row in rows if row.get("strict_failure"))
    failure_reasons = {}
    for row in rows:
        for reason in row.get("failure_reasons") or []:
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
    failed_rows = [
        row for row in rows
        if (row.get("expected_docs") and not row.get("expected_hit"))
        or row.get("unexpected_sources")
        or row.get("strict_failure")
    ]
    mtime = datetime.fromtimestamp(report_path.stat().st_mtime, timezone.utc).isoformat()
    return {
        "available": True,
        "report": {
            "name": report_path.name,
            "path": str(report_path),
            "csv_path": str(report_path.with_suffix(".csv")),
            "md_path": str(report_path.with_suffix(".md")),
            "ragas_path": str(report_path.with_suffix(".ragas.jsonl")),
            "deepeval_path": str(report_stem.with_suffix(".deepeval.json")),
            "updated_at": mtime,
        },
        "summary": {
            "total": len(rows),
            "answerable": len(answerable_rows),
            "expected_hits": expected_hits,
            "recall_at_k": expected_hits / len(answerable_rows) if answerable_rows else 0,
            "top1_hit_rate": top1_hits / len(answerable_rows) if answerable_rows else 0,
            "mrr": reciprocal_rank_total / len(answerable_rows) if answerable_rows else 0,
            "evidence_hit_rate": evidence_hits / len(evidence_rows) if evidence_rows else manual_summary.get("evidence_hit_rate", 0),
            "evidence_hits": evidence_hits or manual_summary.get("evidence_hits", 0),
            "evidence_total": len(evidence_rows) or manual_summary.get("evidence_total", 0),
            "citation_rate": (
                sum(1 for row in citation_rows if row.get("answer_has_citation")) / len(citation_rows)
                if citation_rows else 0
            ),
            "abstention_accuracy": abstention_correct / len(unknown_rows) if unknown_rows else 0,
            "unexpected_sources": unexpected_sources,
            "missing_citations": missing_citations,
            "strict_failures": strict_failures,
            "failure_reasons": failure_reasons,
            "unknown": len(unknown_rows),
            "failed_count": len(failed_rows),
            "average_score": manual_summary.get("average_score"),
        },
        "rows": rows[:100],
        "failed_rows": failed_rows[:20],
    }
