# -*- coding: utf-8 -*-

import hashlib
import re
from datetime import datetime
from pathlib import Path

import vector_store
from config import PROJECT_ROOT


ALLOWED_KNOWLEDGE_EXTENSIONS = {".md", ".txt"}
KNOWLEDGE_FILES_DIR = PROJECT_ROOT / "knowledge_files"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


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
    """
    通过文件指纹查找已存在的文档 ID
    
    策略：
    1. 先匹配快速指纹（文件名+大小）
    2. 如果匹配，再验证内容哈希
    3. 如果快速指纹不匹配，尝试仅用内容哈希匹配
    """
    if not fingerprint:
        return None
    
    # 先查询所有文档的元数据，查找匹配的
    # 这里假设你有一个表存储文档元数据
    # 暂时用简化版实现
    return None


def make_document_id(path: Path, fingerprint: dict = None) -> str:
    """
    生成文档 ID 的改进版
    
    策略：
    1. 如果有指纹且能匹配到现有文档，复用现有 ID
    2. 否则，用标准化文件名生成新 ID
    """
    # 先尝试通过指纹找现有文档
    if fingerprint:
        existing_id = find_existing_document_by_fingerprint(fingerprint)
        if existing_id:
            return existing_id
    
    # 如果没找到，用标准化路径生成新 ID
    relative_path = path.relative_to(PROJECT_ROOT)
    
    # 标准化路径中的每个部分
    normalized_parts = [normalize_filename(part) for part in relative_path.parts]
    normalized_raw_id = "__".join(normalized_parts)
    
    return normalized_raw_id


def resolve_knowledge_file(path):
    target = (PROJECT_ROOT / path).resolve()

    try:
        target.relative_to(PROJECT_ROOT)
    except ValueError:
        return None, f"path is outside project: {path}"

    if not target.is_file():
        return None, f"file not found: {path}"

    if target.suffix.lower() not in ALLOWED_KNOWLEDGE_EXTENSIONS:
        return None, f"file extension is not supported: {path}"

    return target, None


def make_index_text(text, notes=None):
    clean_notes = " ".join((notes or "").split())
    if not clean_notes:
        return text

    return f"{text}\n\nUpload notes: {clean_notes}"


def normalize_notes(notes):
    clean_notes = " ".join((notes or "").split())
    return clean_notes or None


def index_file(path, document_id=None, embedding_client=None, notes=None, force_reindex=False):
    target, error = resolve_knowledge_file(path)
    if error:
        return None, error

    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None, f"file is not valid UTF-8 text: {path}"
    except OSError as error:
        return None, str(error)
    
    # 计算文件指纹
    fingerprint = compute_file_fingerprint(target)
    
    # 如果没有指定 document_id，用智能方式生成
    if document_id is None:
        document_id = make_document_id(target, fingerprint)
    
    normalized_notes = normalize_notes(notes)
    
    existing_chunks = []
    # 检查是否可以跳过索引（内容没变）
    if not force_reindex and fingerprint and fingerprint["content_hash"]:
        # 检查是否已有相同内容的文档
        existing_chunks = vector_store.list_document_chunks(document_id)
        if existing_chunks:
            # 比较内容哈希（这里简化处理，实际应该存储文档级别的哈希）
            # 暂时先跳过这个检查，直接索引
            pass
    
    chunk_count = vector_store.upsert_document(
        document_id,
        make_index_text(text, normalized_notes),
        embedding_client=embedding_client,
    )
    
    # 更新文档元数据
    # 如果有指纹，序列化为 JSON 存储
    if fingerprint:
        import json
        metadata_dict = {
            "user_notes": normalized_notes,
            "fingerprint": fingerprint,
            "indexed_at": datetime.utcnow().isoformat()
        }
        metadata_notes = json.dumps(metadata_dict, ensure_ascii=False)
    else:
        metadata_notes = normalized_notes
    
    vector_store.upsert_document_metadata(document_id, metadata_notes)

    return {
        "document_id": document_id,
        "path": str(target.relative_to(PROJECT_ROOT)),
        "chunk_count": chunk_count,
        "notes": normalized_notes,
        "fingerprint": fingerprint,
        "is_new": not existing_chunks if 'existing_chunks' in locals() else True
    }, None


def safe_upload_name(filename):
    name = Path(filename or "").name.strip()
    if not name:
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
    except OSError as error:
        return None, str(error)
    finally:
        upload_file.file.close()

    return target, None


def upload_and_index_file(upload_file, document_id=None, embedding_client=None, notes=None):
    target, error = save_upload_file(upload_file)
    if error:
        return None, error

    relative_path = target.relative_to(PROJECT_ROOT)
    return index_file(str(relative_path), document_id, embedding_client, notes=notes)
