# -*- coding: utf-8 -*-

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import document_parsers
import vector_store
from config import PROJECT_ROOT


ALLOWED_KNOWLEDGE_EXTENSIONS = {
    ".md", ".rst",          # 文本格式
    ".html", ".htm",        # HTML 格式
    ".docx", ".doc",        # Word 文档
    ".pdf",                 # PDF 文档
    ".csv", ".xlsx", ".xls" # 表格格式（简单支持）
}
KNOWLEDGE_FILES_DIR = PROJECT_ROOT / "knowledge_files"
SYSTEM_METADATA_KEYS = {
    "user_notes",
    "fingerprint",
    "indexed_at",
    "source_path",
    "file_name",
    "file_ext",
    "file_size",
    "category",
    "tags",
}
ALLOWED_USER_METADATA_KEYS = {
    "canonical_id",
    "department",
    "doc_type",
    "document_group",
    "effective_date",
    "expiry_date",
    "owner",
    "policy_id",
    "sensitivity",
    "status",
    "version",
}
ALLOWED_SENSITIVITY_VALUES = {
    "public",
    "internal",
    "confidential",
    "restricted",
}
ALLOWED_STATUS_VALUES = {
    "active",
    "draft",
    "deprecated",
    "archived",
    "inactive",
}
ALLOWED_DOC_TYPE_VALUES = {
    "contract",
    "faq",
    "guide",
    "manual",
    "other",
    "policy",
    "procedure",
    "reference",
}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_UPLOAD_FILENAME_LENGTH = 120
WINDOWS_RESERVED_FILENAMES = {
    "con", "prn", "aux", "nul",
    "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
    "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
}


def resolve_project_path(path_value):
    raw_path = Path(str(path_value))
    return raw_path.resolve() if raw_path.is_absolute() else (PROJECT_ROOT / raw_path).resolve()


def store_path_value(path_value):
    resolved = resolve_project_path(path_value)
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def normalize_metadata_text(value, field_name, max_length=200):
    if value in (None, ""):
        return None, None
    if isinstance(value, (dict, list, tuple, set)):
        return None, f"metadata.{field_name} must be a string"

    normalized = " ".join(str(value).split())
    if not normalized:
        return None, None
    if len(normalized) > max_length:
        return None, f"metadata.{field_name} is longer than {max_length} characters"
    return normalized, None


def normalize_metadata_enum(value, field_name, allowed_values):
    normalized, error = normalize_metadata_text(value, field_name, max_length=80)
    if error or normalized is None:
        return normalized, error

    normalized = normalized.lower()
    if normalized not in allowed_values:
        allowed = ", ".join(sorted(allowed_values))
        return None, f"metadata.{field_name} must be one of: {allowed}"
    return normalized, None


def normalize_metadata_date(value, field_name):
    normalized, error = normalize_metadata_text(value, field_name, max_length=40)
    if error or normalized is None:
        return normalized, error

    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(normalized[:10], "%Y-%m-%d")
        except ValueError:
            return None, f"metadata.{field_name} must be an ISO date or datetime"

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(), None


def validate_document_metadata(metadata, *, require_department=False):
    if metadata is None:
        if require_department:
            return None, "metadata.department is required"
        return {}, None
    if not isinstance(metadata, dict):
        return None, "metadata must be an object"

    normalized_metadata = {}
    unknown_keys = sorted(
        key
        for key in metadata.keys()
        if key not in ALLOWED_USER_METADATA_KEYS and key not in SYSTEM_METADATA_KEYS
    )
    if unknown_keys:
        return None, f"unsupported metadata keys: {', '.join(unknown_keys)}"

    for key, value in metadata.items():
        if key in SYSTEM_METADATA_KEYS:
            continue
        if value in (None, "", []):
            continue

        if key in {"sensitivity"}:
            normalized, error = normalize_metadata_enum(value, key, ALLOWED_SENSITIVITY_VALUES)
        elif key in {"status"}:
            normalized, error = normalize_metadata_enum(value, key, ALLOWED_STATUS_VALUES)
        elif key in {"doc_type"}:
            normalized, error = normalize_metadata_enum(value, key, ALLOWED_DOC_TYPE_VALUES)
        elif key in {"effective_date", "expiry_date"}:
            normalized, error = normalize_metadata_date(value, key)
        else:
            normalized, error = normalize_metadata_text(value, key)

        if error:
            return None, error
        if normalized is not None:
            normalized_metadata[key] = normalized

    if require_department and not normalized_metadata.get("department"):
        return None, "metadata.department is required"

    effective_date = normalized_metadata.get("effective_date")
    expiry_date = normalized_metadata.get("expiry_date")
    if effective_date and expiry_date:
        effective_at = datetime.fromisoformat(effective_date)
        expiry_at = datetime.fromisoformat(expiry_date)
        if expiry_at < effective_at:
            return None, "metadata.expiry_date must not be earlier than metadata.effective_date"

    return normalized_metadata, None


def normalize_filename(filename: str) -> str:
    """
    标准化文件名，忽略空格、大小写、特殊字符差异
    """
    # 转为小写
    normalized = filename.lower()
    
    # 移除或替换特殊字符
    # 把多个空格/下划线/连字符替换为单个下划线
    normalized = re.sub(r'[\s\-_]+', '_', normalized)
    
    # 移除其他特殊字符（保留字母数字下划线点）
    normalized = re.sub(r'[^a-z0-9_\.]', '', normalized)
    
    # 移除开头结尾的下划线
    normalized = normalized.strip('_')
    
    return normalized


def compute_file_fingerprint(file_path: Path) -> dict:
    """
    计算文件指纹，用于识别是否是同一文件（即使文件名有小变化）
    
    返回：
    {
        "content_hash": "文件内容的 SHA-256 哈希",
        "size": 文件大小（字节）,
        "normalized_name": "标准化的文件名",
        "file_ext": "文件扩展名",
        "fast_fingerprint": "快速指纹（大小 + 标准化文件名的哈希）"
    }
    """
    if not file_path.exists():
        return None
    
    # 读取文件内容计算哈希
    try:
        content = file_path.read_bytes()
        content_hash = hashlib.sha256(content).hexdigest()
    except Exception:
        content_hash = None
    
    # 获取文件信息
    stat = file_path.stat()
    size = stat.st_size
    
    # 标准化文件名
    normalized_name = normalize_filename(file_path.name)
    
    # 快速指纹（不依赖内容，用于快速过滤）
    fast_hash_input = f"{size}_{normalized_name}".encode('utf-8')
    fast_fingerprint = hashlib.md5(fast_hash_input).hexdigest()
    
    return {
        "content_hash": content_hash,
        "size": size,
        "normalized_name": normalized_name,
        "file_ext": file_path.suffix.lower(),
        "fast_fingerprint": fast_fingerprint
    }


def find_existing_document_by_fingerprint(fingerprint: dict) -> str | None:
    if not fingerprint:
        return None
    return vector_store.find_document_by_content_hash(fingerprint.get("content_hash"))


def make_document_id(path: Path, fingerprint: dict = None, use_original_name: bool = False) -> str:
    """
    生成文档 ID 的改进版
    
    策略：
    1. 如果有指纹且能匹配到现有文档，复用现有 ID
    2. 如果 use_original_name=True（上传的文件），保留原始文件名
    3. 否则，用标准化文件名生成新 ID
    """
    # 先尝试通过指纹找现有文档
    if fingerprint:
        existing_id = find_existing_document_by_fingerprint(fingerprint)
        if existing_id:
            return existing_id
    
    # 如果是上传的文件且保留原始文件名
    if use_original_name:
        return path.name
    
    # 如果没找到，用标准化路径生成新 ID
    relative_path = path.relative_to(PROJECT_ROOT)
    
    # 标准化路径中的每个部分
    normalized_parts = [normalize_filename(part) for part in relative_path.parts]
    normalized_raw_id = "__".join(normalized_parts)
    
    return normalized_raw_id


def resolve_knowledge_file(path):
    target = resolve_project_path(path)

    try:
        target.relative_to(PROJECT_ROOT)
        allowed = True
    except ValueError:
        allowed = is_registered_source_file(target)

    if not allowed:
        return None, f"path is outside project or registered sources: {path}"

    if not target.is_file():
        return None, f"file not found: {path}"

    if target.suffix.lower() not in ALLOWED_KNOWLEDGE_EXTENSIONS:
        return None, f"file extension is not supported: {path}"

    return target, None


def is_registered_source_file(target):
    try:
        import database

        resolved = Path(target).resolve()
        for source in database.list_knowledge_sources():
            if source["type"] != "local_folder" or not source["enabled"]:
                continue
            try:
                resolved.relative_to(resolve_project_path(source["path"]))
                return True
            except ValueError:
                continue
    except Exception:
        return False
    return False


def make_index_text(text, notes=None):
    clean_notes = " ".join((notes or "").split())
    if not clean_notes:
        return text

    return f"{text}\n\nUpload notes: {clean_notes}"


def normalize_notes(notes):
    clean_notes = " ".join((notes or "").split())
    return clean_notes or None


def apply_notes_to_segments(segments, notes=None):
    clean_notes = normalize_notes(notes)
    if not clean_notes or not segments:
        return segments

    updated_segments = [dict(segment) for segment in segments]
    updated_segments[0]["text"] = make_index_text(updated_segments[0].get("text", ""), clean_notes)
    updated_segments[0]["metadata"] = dict(updated_segments[0].get("metadata") or {})
    updated_segments[0]["metadata"]["has_user_notes"] = True
    return updated_segments


def index_file(path, document_id=None, embedding_client=None, notes=None, category=None, tags=None, metadata=None, force_reindex=False, use_original_name=False):
    target, error = resolve_knowledge_file(path)
    if error:
        return None, error
    normalized_metadata, error = validate_document_metadata(metadata)
    if error:
        return None, error

    # 使用文档解析器读取文件内容
    text, parse_error = document_parsers.parse_document(target)
    segments, parse_error = document_parsers.parse_document_segments(target)
    if parse_error:
        return None, parse_error
    if not segments:
        return None, "no readable text found in document"
    
    # 计算文件指纹
    fingerprint = compute_file_fingerprint(target)
    
    # 如果没有指定 document_id，用智能方式生成
    if document_id is None:
        document_id = make_document_id(target, fingerprint, use_original_name=use_original_name)
    duplicate_of = None
    if fingerprint and fingerprint.get("content_hash"):
        duplicate_of = vector_store.find_document_by_content_hash(
            fingerprint["content_hash"],
            exclude_document_id=document_id,
        )
    if duplicate_of:
        vector_store.delete_document(document_id)
        existing_metadata = vector_store.get_document_metadata(duplicate_of) or {}
        existing_chunks = vector_store.list_document_chunks(duplicate_of)
        try:
            result_path = target.relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            result_path = str(target)
        return {
            "document_id": duplicate_of,
            "path": result_path,
            "chunk_count": len(existing_chunks),
            "notes": existing_metadata.get("user_notes"),
            "fingerprint": fingerprint,
            "category": existing_metadata.get("category") or category or "uncategorized",
            "tags": existing_metadata.get("tags") or tags or [],
            "metadata": normalized_metadata,
            "is_new": False,
            "deduplicated": True,
            "duplicate_of": duplicate_of,
        }, None
    
    normalized_notes = normalize_notes(notes)
    source_path = store_path_value(target)

    if not force_reindex and fingerprint and fingerprint.get("content_hash"):
        current_chunks = vector_store.list_document_chunks(document_id)
        if current_chunks:
            current_metadata = vector_store.get_document_metadata(document_id) or {}
            current_fingerprint = current_metadata.get("fingerprint") if isinstance(current_metadata, dict) else None
            if (
                isinstance(current_fingerprint, dict)
                and current_fingerprint.get("content_hash") == fingerprint["content_hash"]
            ):
                metadata_dict = {
                    "user_notes": normalized_notes,
                    "fingerprint": fingerprint,
                    "indexed_at": datetime.now(timezone.utc).isoformat(),
                    "source_path": source_path,
                    "file_name": target.name,
                    "file_ext": target.suffix.lower(),
                    "file_size": target.stat().st_size,
                    "category": category or "uncategorized",
                    "tags": tags or [],
                    "index_skipped_reason": "unchanged_content_hash",
                }
                metadata_dict.update(normalized_metadata)
                vector_store.upsert_document_metadata(document_id, json.dumps(metadata_dict, ensure_ascii=False))
                return {
                    "document_id": document_id,
                    "path": source_path,
                    "chunk_count": len(current_chunks),
                    "notes": normalized_notes,
                    "fingerprint": fingerprint,
                    "category": category or "uncategorized",
                    "tags": tags or [],
                    "metadata": normalized_metadata,
                    "is_new": False,
                    "skipped": True,
                    "skip_reason": "unchanged_content_hash",
                }, None
    
    existing_chunks = []
    # 检查是否可以跳过索引（内容没变）
    if not force_reindex and fingerprint and fingerprint["content_hash"]:
        # 检查是否已有相同内容的文档
        existing_chunks = vector_store.list_document_chunks(document_id)
        if existing_chunks:
            # 比较内容哈希（这里简化处理，实际应该存储文档级别的哈希）
            # 暂时先跳过这个检查，直接索引
            pass
    
    chunk_count = vector_store.upsert_document_segments(
        document_id,
        apply_notes_to_segments(segments, normalized_notes),
        embedding_client=embedding_client,
    )
    
    # 更新文档元数据（包含分类和标签）
    if fingerprint:
        metadata_dict = {
            "user_notes": normalized_notes,
            "fingerprint": fingerprint,
            "indexed_at": datetime.now(timezone.utc).isoformat(),
            "source_path": source_path,
            "file_name": target.name,
            "file_ext": target.suffix.lower(),
            "file_size": target.stat().st_size,
            "category": category or "uncategorized",
            "tags": tags or []
        }
        metadata_dict.update(normalized_metadata)
        metadata_notes = json.dumps(metadata_dict, ensure_ascii=False)
    else:
        metadata_notes = normalized_notes
    
    vector_store.upsert_document_metadata(document_id, metadata_notes)

    result_path = source_path

    return {
        "document_id": document_id,
        "path": result_path,
        "chunk_count": chunk_count,
        "notes": normalized_notes,
        "fingerprint": fingerprint,
        "category": category or "uncategorized",
        "tags": tags or [],
        "metadata": normalized_metadata,
        "is_new": not existing_chunks if 'existing_chunks' in locals() else True
    }, None


def source_path_from_metadata(document_id, metadata=None):
    metadata = metadata or vector_store.get_document_metadata(document_id) or {}
    source_path = metadata.get("source_path") if isinstance(metadata, dict) else None
    candidates = []

    if source_path:
        candidates.append(resolve_project_path(source_path))

    candidates.append(KNOWLEDGE_FILES_DIR / document_id)

    for candidate in candidates:
        resolved = candidate.resolve()
        try:
            resolved.relative_to(PROJECT_ROOT)
            allowed = True
        except ValueError:
            allowed = is_registered_source_file(resolved)
        if not allowed:
            continue
        if resolved.is_file():
            return resolved

    return None


def delete_uploaded_source_file(document_id, metadata=None):
    source_path = source_path_from_metadata(document_id, metadata)
    if source_path is None:
        return None

    try:
        source_path.relative_to(KNOWLEDGE_FILES_DIR.resolve())
    except ValueError:
        return None

    source_path.unlink()
    return source_path.relative_to(PROJECT_ROOT).as_posix()


def safe_upload_name(filename):
    name = Path(filename or "").name.strip()
    if not name:
        return None

    if len(name) > MAX_UPLOAD_FILENAME_LENGTH:
        return None

    if any(ord(char) < 32 for char in name):
        return None

    if name.endswith((".", " ")):
        return None

    if Path(name).stem.lower() in WINDOWS_RESERVED_FILENAMES:
        return None

    if Path(name).suffix.lower() not in ALLOWED_KNOWLEDGE_EXTENSIONS:
        return None

    return name


def save_upload_file(upload_file):
    safe_name = safe_upload_name(upload_file.filename)
    if not safe_name:
        return None, "file extension is not supported"

    KNOWLEDGE_FILES_DIR.mkdir(parents=True, exist_ok=True)
    target = (KNOWLEDGE_FILES_DIR / safe_name).resolve()

    try:
        target.relative_to(KNOWLEDGE_FILES_DIR.resolve())
    except ValueError:
        return None, "invalid upload file name"

    total_bytes = 0
    try:
        with target.open("wb") as output:
            while True:
                chunk = upload_file.file.read(1024 * 1024)
                if not chunk:
                    break

                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_BYTES:
                    output.close()
                    target.unlink(missing_ok=True)
                    return None, "file is larger than 50MB"

                output.write(chunk)
    except OSError:
        return None, "failed to save upload file"
    finally:
        upload_file.file.close()

    return target, None



