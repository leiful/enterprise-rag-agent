# -*- coding: utf-8 -*-

from datetime import datetime, timezone

from config import REQUIRE_DOCUMENT_DEPARTMENT


def normalize_department(value):
    return " ".join(str(value or "").split()).lower()


def normalize_departments(departments):
    if departments is None:
        return None
    return {
        normalized
        for normalized in (normalize_department(department) for department in departments)
        if normalized
    }


def document_department(metadata):
    if not isinstance(metadata, dict):
        return ""
    return normalize_department(metadata.get("department"))


def document_sensitivity(metadata):
    if not isinstance(metadata, dict):
        return ""
    return " ".join(str(metadata.get("sensitivity") or "").split()).lower()


def can_access_document(metadata, allowed_departments):
    normalized_departments = normalize_departments(allowed_departments)
    if normalized_departments is None:
        return True

    if document_sensitivity(metadata) == "public":
        return True

    department = document_department(metadata)
    if not department:
        return not REQUIRE_DOCUMENT_DEPARTMENT

    return department in normalized_departments


def parse_metadata_datetime(value):
    if not value:
        return None

    text = str(value).strip()
    if not text:
        return None

    try:
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed = datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def document_lifecycle_status(metadata, now=None):
    if not isinstance(metadata, dict):
        return "active"

    status = str(metadata.get("status") or metadata.get("document_status") or "").strip().lower()
    if status in {"draft", "deprecated", "archived", "inactive"}:
        return status

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)

    effective_at = parse_metadata_datetime(metadata.get("effective_date"))
    if effective_at and effective_at > now:
        return "not_yet_effective"

    expiry_at = parse_metadata_datetime(metadata.get("expiry_date"))
    if expiry_at and expiry_at < now:
        return "expired"

    return "active"


def is_document_active(metadata, now=None):
    return document_lifecycle_status(metadata, now=now) == "active"


def document_version_group(document_id, metadata):
    if isinstance(metadata, dict):
        for key in ("canonical_id", "document_group", "policy_id"):
            value = metadata.get(key)
            if value:
                return str(value).strip().lower()
    return str(document_id or "").strip().lower()


def parse_version_sort_key(value):
    if value in (None, ""):
        return ()

    parts = []
    for part in str(value).strip().replace("-", ".").replace("_", ".").split("."):
        if part.isdigit():
            parts.append((1, int(part)))
        elif part:
            parts.append((0, part.lower()))
    return tuple(parts)
