# -*- coding: utf-8 -*-

import logging
from contextvars import ContextVar

import database
from app_logging import get_logger, log_event


logger = get_logger("backend.model_usage")
usage_scope_var = ContextVar("usage_scope", default="other")
usage_metadata_var = ContextVar("usage_metadata", default={})


def set_usage_scope(scope):
    return usage_scope_var.set(scope or "other")


def reset_usage_scope(token):
    try:
        usage_scope_var.reset(token)
    except ValueError:
        usage_scope_var.set("other")


def set_usage_metadata(metadata):
    return usage_metadata_var.set(dict(metadata or {}))


def reset_usage_metadata(token):
    try:
        usage_metadata_var.reset(token)
    except ValueError:
        usage_metadata_var.set({})


def estimate_tokens(text):
    if text is None:
        return 0
    return max(1, round(len(str(text)) / 4)) if str(text) else 0


def record_model_usage(
    *,
    provider,
    model,
    operation,
    request_id=None,
    input_texts=None,
    output_texts=None,
    document_count=0,
    metadata=None,
):
    if model == "test-model":
        return

    input_texts = input_texts or []
    output_texts = output_texts or []
    input_chars = sum(len(str(text or "")) for text in input_texts)
    output_chars = sum(len(str(text or "")) for text in output_texts)
    input_tokens = sum(estimate_tokens(text) for text in input_texts)
    output_tokens = sum(estimate_tokens(text) for text in output_texts)

    try:
        event_metadata = dict(usage_metadata_var.get() or {})
        event_metadata.update(dict(metadata or {}))
        event_metadata.setdefault("scope", usage_scope_var.get())
        database.add_model_usage_event(
            provider=provider,
            model=model,
            operation=operation,
            request_id=request_id,
            input_tokens_estimate=input_tokens,
            output_tokens_estimate=output_tokens,
            input_chars=input_chars,
            output_chars=output_chars,
            document_count=document_count,
            metadata=event_metadata,
        )
    except Exception as error:
        log_event(
            logger,
            logging.WARNING,
            "model_usage_record_failed",
            provider=provider,
            model=model,
            operation=operation,
            error=str(error),
        )
