# -*- coding: utf-8 -*-

import json
import logging
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app_logging import get_logger, log_event, request_id_var
from config import (
    RERANK_API_KEY,
    RERANK_API_URL,
    RERANK_MAX_CANDIDATES,
    RERANK_MIN_SCORE,
    RERANK_MODEL,
)
from model_usage import record_model_usage


logger = get_logger("backend.rerank")


def rerank_with_dashscope(query, candidates, top_k=3):
    if not candidates:
        return []

    if not RERANK_API_KEY:
        return candidates[:top_k]

    original_candidate_count = len(candidates)
    candidates = candidates[:RERANK_MAX_CANDIDATES]
    documents = [candidate.text for candidate in candidates]
    request_id = request_id_var.get()
    payload = {
        "model": RERANK_MODEL,
        "input": {
            "query": query,
            "documents": documents,
        },
        "parameters": {
            "return_documents": False,
            "top_n": min(top_k, len(candidates)),
        },
    }
    request = Request(
        RERANK_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {RERANK_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    started_at = time.perf_counter()
    log_event(
        logger,
        logging.INFO,
        "dashscope_rerank_requested",
        model=RERANK_MODEL,
        candidate_count=len(candidates),
        original_candidate_count=original_candidate_count,
        top_k=top_k,
        query_chars=len(query or ""),
        document_chars=sum(len(text or "") for text in documents),
    )
    try:
        with urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, json.JSONDecodeError) as error:
        log_event(
            logger,
            logging.WARNING,
            "dashscope_rerank_failed",
            candidate_count=len(candidates),
            original_candidate_count=original_candidate_count,
            top_k=top_k,
            error=str(error),
        )
        return candidates[:top_k]

    record_model_usage(
        provider="dashscope",
        model=RERANK_MODEL,
        operation="rerank",
        request_id=request_id,
        input_texts=[query or "", *documents],
        document_count=len(candidates),
        metadata={
            "top_k": top_k,
            "original_candidate_count": original_candidate_count,
            "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
        },
    )
    log_event(
        logger,
        logging.INFO,
        "dashscope_rerank_completed",
        model=RERANK_MODEL,
        candidate_count=len(candidates),
        original_candidate_count=original_candidate_count,
        top_k=top_k,
        duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
    )

    ranked = []
    for item in data.get("output", {}).get("results", []):
        index = item.get("index")
        score = item.get("relevance_score")
        if not isinstance(index, int) or not 0 <= index < len(candidates):
            continue

        candidate = candidates[index]
        if isinstance(score, (int, float)):
            candidate.score = float(score)
        ranked.append(candidate)

    if not ranked:
        return candidates[:top_k]

    ranked = ranked[:top_k]
    filtered = [candidate for candidate in ranked if candidate.score >= RERANK_MIN_SCORE]
    return filtered or ranked[:top_k]
