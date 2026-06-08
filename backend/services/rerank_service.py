# -*- coding: utf-8 -*-

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app_logging import get_logger, log_event
from config import (
    RERANK_API_KEY,
    RERANK_API_URL,
    RERANK_MIN_SCORE,
    RERANK_MODEL,
)


logger = get_logger("backend.rerank")


def rerank_with_dashscope(query, candidates, top_k=3):
    if not candidates:
        return []

    if not RERANK_API_KEY:
        return candidates[:top_k]

    payload = {
        "model": RERANK_MODEL,
        "input": {
            "query": query,
            "documents": [candidate.text for candidate in candidates],
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

    try:
        with urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, json.JSONDecodeError) as error:
        log_event(
            logger,
            logging.WARNING,
            "dashscope_rerank_failed",
            candidate_count=len(candidates),
            top_k=top_k,
            error=str(error),
        )
        return candidates[:top_k]

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
