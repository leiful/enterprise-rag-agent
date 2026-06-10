# -*- coding: utf-8 -*-

import importlib.util
import json
import os
from pathlib import Path
import secrets
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

import app_state
from AI_agent import build_knowledge_preflight, run_agent, search_knowledge_payload
from app_logging import get_logger, log_event
from config import (
    BASE_URL,
    DEFAULT_KNOWLEDGE_MIN_SCORE,
    DEFAULT_KNOWLEDGE_TOP_K,
    ENABLE_MULTI_QUERY,
    ENABLE_QUERY_REWRITE,
    ENABLE_RERANK,
    MIN_EVIDENCE_SOURCES,
    RECALL_K,
    RERANK_MAX_CANDIDATES,
    REQUIRE_DOCUMENT_DEPARTMENT,
    STRICT_KNOWLEDGE_ABSTENTION,
    SYSTEM_MESSAGE,
)
from database import (
    acknowledge_failed_index_jobs,
    add_admin_audit_event,
    add_knowledge_access_audit,
    connect,
    count_admin_audit_events,
    count_knowledge_access_audit,
    create_index_job,
    delete_missing_knowledge_source_files,
    get_bm25_stats,
    get_index_job,
    get_index_job_status_counts,
    get_knowledge_source_file_status_counts,
    get_unacknowledged_failed_index_job_count,
    list_failed_index_jobs,
    reassign_knowledge_source_files,
    summarize_model_usage,
    summarize_rag_feedback,
    update_index_job,
    update_knowledge_source_file_by_job,
)
from dependencies import require_admin, user_knowledge_departments
import knowledge
import knowledge_sources
import model_usage
import rag_eval_runtime
import tools
from schemas import (
    AcknowledgeIndexJobsRequest,
    DeepSeekBalanceResponse,
    IndexFileRequest,
    IndexJobResponse,
    RagEvalRunRequest,
    SearchKnowledgeRequest,
)
import vector_store

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import rag_eval as rag_eval_script


router = APIRouter()
logger = get_logger("backend.operations")
@router.get("/admin/rag/status", dependencies=[Depends(require_admin)])
def admin_rag_status():
    return get_rag_operational_status()


@router.get("/admin/rag/eval", dependencies=[Depends(require_admin)])
def admin_rag_eval():
    return latest_rag_eval_report()


@router.get("/admin/rag/eval/suites", dependencies=[Depends(require_admin)])
def admin_rag_eval_suites():
    return {"suites": rag_eval_suite_list()}


@router.post("/admin/rag/eval/run", dependencies=[Depends(require_admin)])
def admin_run_rag_eval(request_data: RagEvalRunRequest, user=Depends(require_admin)):
    scope_token = model_usage.set_usage_scope("evaluation")
    try:
        result = run_rag_eval_suite(
            request_data.suite,
            skip_chat=request_data.skip_chat,
            skip_upload=request_data.skip_upload,
            skip_search=request_data.skip_search,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    except (FileNotFoundError, RuntimeError) as error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error))
    finally:
        model_usage.reset_usage_scope(scope_token)

    add_admin_audit_event(
        user,
        "rag_eval.run",
        "rag_eval",
        target_id=request_data.suite,
        details=result,
    )
    return result


def document_ocr_available():
    return importlib.util.find_spec("pytesseract") is not None


def project_root():
    return Path(__file__).resolve().parents[2]


RAG_EVAL_SUITES = rag_eval_runtime.build_default_rag_eval_suites(project_root())


def answer_abstained(answer):
    return rag_eval_runtime.answer_abstained(answer)


def answer_has_citation(answer):
    return rag_eval_runtime.answer_has_citation(answer)


def eval_evidence_terms_score(row):
    return rag_eval_runtime.eval_evidence_terms_score(row)


def rag_eval_suite_list():
    return rag_eval_runtime.rag_eval_suite_list(RAG_EVAL_SUITES)


def index_rag_eval_docs(docs_dir):
    return rag_eval_runtime.index_rag_eval_docs(
        docs_dir,
        project_root=project_root(),
        knowledge_module=knowledge,
    )


def run_rag_eval_suite(suite_id, *, skip_chat=False, skip_upload=False, skip_search=False):
    def search_callback(query, top_k, min_score):
        return search_knowledge_payload(
            query,
            top_k=top_k,
            min_score=min_score,
            client=app_state.client,
        )

    def chat_callback(message, conversation_id=None):
        messages = [SYSTEM_MESSAGE.copy()]
        knowledge_preflight = build_knowledge_preflight(message, client=app_state.client, messages=messages)
        result = run_agent(
            app_state.client,
            messages,
            message,
            knowledge_preflight=knowledge_preflight,
            return_sources=True,
        )
        if isinstance(result, dict):
            return {
                "answer": result.get("answer", ""),
                "sources": result.get("sources") or knowledge_preflight.get("sources") or [],
                "conversation_id": conversation_id,
            }
        return {
            "answer": str(result),
            "sources": knowledge_preflight.get("sources") or [],
            "conversation_id": conversation_id,
        }

    return rag_eval_runtime.run_rag_eval_suite(
        suite_id,
        suites=RAG_EVAL_SUITES,
        project_root=project_root(),
        rag_eval_script=rag_eval_script,
        search_callback=search_callback,
        chat_callback=chat_callback,
        index_docs_callback=index_rag_eval_docs,
        skip_chat=skip_chat,
        skip_upload=skip_upload,
        skip_search=skip_search,
    )


def latest_rag_eval_report():
    return rag_eval_runtime.latest_rag_eval_report(project_root())


def search_result_to_source(result):
    metadata = result.metadata or {}
    return {
        "score": result.score,
        "chunk_id": result.chunk_id,
        "document_id": result.document_id,
        "chunk_index": result.chunk_index,
        "metadata": metadata,
        "page_start": metadata.get("page_start"),
        "page_end": metadata.get("page_end"),
        "text": result.text,
    }


def parse_tags_field(tags: str | None):
    if not tags:
        return None
    try:
        return json.loads(tags)
    except Exception:
        return [tag.strip() for tag in tags.split(",") if tag.strip()]


def parse_metadata_field(metadata: str | None):
    if not metadata:
        return None
    try:
        parsed = json.loads(metadata)
    except json.JSONDecodeError as error:
        raise ValueError(f"metadata must be valid JSON: {error.msg}")
    if not isinstance(parsed, dict):
        raise ValueError("metadata must be a JSON object")
    return parsed


def run_index_job(
    job_id: str,
    path: str,
    document_id: str | None,
    notes: str | None,
    category: str | None,
    tags: list[str] | None,
    metadata: dict | None,
    use_original_name: bool,
    force_reindex: bool = False,
):
    scope_token = model_usage.set_usage_scope("indexing")
    metadata_token = model_usage.set_usage_metadata({
        "job_id": job_id,
        "document_id": document_id,
        "path": path,
        "force_reindex": force_reindex,
    })
    update_index_job(job_id, status="running")
    start = time.perf_counter()
    log_event(
        logger,
        20,
        "knowledge_index_job_started",
        job_id=job_id,
        document_id=document_id,
        path=path,
        category=category,
        tags=tags or [],
        metadata=metadata or {},
    )
    try:
        result, error = knowledge.index_file(
            path,
            document_id,
            notes=notes,
            category=category,
            tags=tags,
            metadata=metadata,
            force_reindex=force_reindex,
            use_original_name=use_original_name,
        )
        if error:
            update_index_job(job_id, status="failed", error=error)
            update_knowledge_source_file_by_job(job_id, "failed")
            log_event(
                logger,
                40,
                "knowledge_index_job_failed",
                job_id=job_id,
                document_id=document_id,
                path=path,
                error=error,
                duration_ms=round((time.perf_counter() - start) * 1000, 2),
            )
            return
        update_index_job(
            job_id,
            status="completed",
            document_id=result.get("document_id"),
            path=result.get("path"),
            result=result,
            error=None,
        )
        update_knowledge_source_file_by_job(job_id, "indexed")
        log_event(
            logger,
            20,
            "knowledge_index_job_completed",
            job_id=job_id,
            document_id=result.get("document_id"),
            path=result.get("path"),
            chunk_count=result.get("chunk_count"),
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
        )
    except Exception as error:
        update_index_job(job_id, status="failed", error=str(error))
        update_knowledge_source_file_by_job(job_id, "failed")
        log_event(
            logger,
            40,
            "knowledge_index_job_exception",
            job_id=job_id,
            document_id=document_id,
            path=path,
            error=str(error),
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
        )
    finally:
        model_usage.reset_usage_metadata(metadata_token)
        model_usage.reset_usage_scope(scope_token)


def enqueue_index_job(
    background_tasks: BackgroundTasks,
    *,
    path: str,
    document_id: str | None,
    notes: str | None,
    category: str | None,
    tags: list[str] | None,
    use_original_name: bool,
    metadata: dict | None = None,
    force_reindex: bool = False,
):
    job_id = secrets.token_urlsafe(16)
    create_index_job(job_id, document_id=document_id, path=path, status="queued")
    background_tasks.add_task(
        run_index_job,
        job_id,
        path,
        document_id,
        notes,
        category,
        tags,
        metadata,
        use_original_name,
        force_reindex,
    )
    return job_id


def get_database_health():
    try:
        with connect() as connection:
            connection.execute("SELECT 1").fetchone()
    except Exception as error:
        return {
            "status": "error",
            "error": str(error),
        }
    return {"status": "ok"}


def get_rag_operational_status():
    documents = vector_store.list_documents()
    total_chunks = sum(int(document.get("chunk_count") or 0) for document in documents)
    sources = knowledge_sources.list_sources()
    source_file_status_counts = get_knowledge_source_file_status_counts()
    index_job_status_counts = get_index_job_status_counts()
    failed_index_jobs = list_failed_index_jobs(limit=20)
    unacknowledged_failed_index_jobs = get_unacknowledged_failed_index_job_count()
    bm25_stats = get_bm25_stats()
    eval_report = latest_rag_eval_report()
    feedback_summary = summarize_rag_feedback()
    model_usage_today = summarize_model_usage(days=1, limit=12)
    model_usage_week = summarize_model_usage(days=7, limit=12)

    enabled_unsynced_sources = [
        source for source in sources
        if source.get("enabled") and not source.get("last_sync_at")
    ]
    missing_source_files = source_file_status_counts.get("missing", 0)

    rag_status = "ok"
    issues = []
    if unacknowledged_failed_index_jobs:
        rag_status = "degraded"
        issues.append({
            "name": "failed_index_jobs",
            "severity": "warning",
            "message": f"{unacknowledged_failed_index_jobs} knowledge index job(s) failed.",
        })
    if missing_source_files:
        rag_status = "degraded"
        issues.append({
            "name": "missing_source_files",
            "severity": "warning",
            "message": f"{missing_source_files} source file(s) are missing and no longer indexed.",
        })
    if enabled_unsynced_sources:
        rag_status = "degraded"
        issues.append({
            "name": "unsynced_sources",
            "severity": "warning",
            "message": f"{len(enabled_unsynced_sources)} enabled knowledge source(s) have not completed a sync.",
        })
    if eval_report.get("available") and eval_report.get("summary", {}).get("failed_count"):
        rag_status = "degraded"
        issues.append({
            "name": "rag_eval_failures",
            "severity": "warning",
            "message": f"{eval_report['summary']['failed_count']} RAG evaluation row(s) need review.",
        })

    return {
        "status": rag_status,
        "issues": issues,
        "documents": {
            "count": len(documents),
            "chunk_count": total_chunks,
        },
        "sources": {
            "count": len(sources),
            "enabled_count": sum(1 for source in sources if source.get("enabled")),
            "file_status_counts": source_file_status_counts,
        },
        "index_jobs": {
            "status_counts": index_job_status_counts,
            "failed_unacknowledged_count": unacknowledged_failed_index_jobs,
            "recent_failed": failed_index_jobs,
        },
        "retrieval": {
            "vector_store_backend": vector_store.VECTOR_STORE_BACKEND,
            "chroma_collection": vector_store.CHROMA_COLLECTION_NAME,
            "bm25_total_docs": bm25_stats.get("total_docs", 0),
            "bm25_avg_doc_len": bm25_stats.get("avg_doc_len", 0.0),
            "query_rewrite_enabled": ENABLE_QUERY_REWRITE,
            "multi_query_enabled": ENABLE_MULTI_QUERY,
            "rerank_enabled": ENABLE_RERANK,
            "rerank_max_candidates": RERANK_MAX_CANDIDATES,
            "recall_k": RECALL_K,
            "default_top_k": DEFAULT_KNOWLEDGE_TOP_K,
            "default_min_score": DEFAULT_KNOWLEDGE_MIN_SCORE,
            "min_evidence_sources": MIN_EVIDENCE_SOURCES,
            "strict_abstention_enabled": STRICT_KNOWLEDGE_ABSTENTION,
            "require_document_department": REQUIRE_DOCUMENT_DEPARTMENT,
        },
        "chat_admission": app_state.current_chat_admission_status(),
        "quality": {
            "latest_eval": eval_report.get("summary", {}) if eval_report.get("available") else {},
        },
        "model_usage": {
            "today": model_usage_today,
            "last_7_days": model_usage_week,
        },
        "parsing": {
            "supported_extensions": sorted(knowledge.ALLOWED_KNOWLEDGE_EXTENSIONS),
            "ocr_available": document_ocr_available(),
            "ocr_note": "Scanned PDFs and image-only files require OCR support before indexing text.",
        },
        "audit": {
            "event_count": count_knowledge_access_audit(),
            "admin_event_count": count_admin_audit_events(),
        },
        "feedback": feedback_summary,
    }


def get_deepseek_balance():
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DEEPSEEK_API_KEY is not configured.",
        )

    request = UrlRequest(
        f"{BASE_URL.rstrip('/')}/user/balance",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"DeepSeek balance request failed with status {error.code}.",
        )
    except (OSError, URLError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"DeepSeek balance request failed: {error}",
        )


@router.get(
    "/billing/deepseek-balance",
    response_model=DeepSeekBalanceResponse,
    dependencies=[Depends(require_admin)],
)
def deepseek_balance():
    return get_deepseek_balance()


@router.get("/files", dependencies=[Depends(require_admin)])
def files():
    backend_dir = Path(__file__).resolve().parents[1]
    names = sorted(path.name for path in backend_dir.iterdir() if path.is_file())
    return {"files": names}


@router.post("/knowledge/index-file", dependencies=[Depends(require_admin)])
def index_knowledge_file(request: IndexFileRequest, background_tasks: BackgroundTasks, user=Depends(require_admin)):
    target, error = knowledge.resolve_knowledge_file(request.path)
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )
    normalized_metadata, error = knowledge.validate_document_metadata(request.metadata)
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    resolved_document_id = request.document_id
    if resolved_document_id is None:
        resolved_document_id = knowledge.make_document_id(target, use_original_name=False)

    job_id = enqueue_index_job(
        background_tasks,
        path=request.path,
        document_id=resolved_document_id,
        notes=request.notes,
        category=request.category,
        tags=request.tags,
        use_original_name=False,
        metadata=normalized_metadata,
    )
    add_admin_audit_event(
        user,
        "knowledge.index_file",
        "knowledge_document",
        target_id=resolved_document_id,
        details={
            "job_id": job_id,
            "path": request.path,
            "category": request.category,
            "tags": request.tags or [],
        },
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=IndexJobResponse(
            job_id=job_id,
            status="queued",
            document_id=resolved_document_id,
            path=request.path,
            result=None,
            error=None,
        ).model_dump(),
    )


@router.post("/knowledge/upload", dependencies=[Depends(require_admin)])
def upload_knowledge_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    notes: str | None = Form(default=None),
    category: str | None = Form(default=None),
    tags: str | None = Form(default=None),
    metadata: str | None = Form(default=None),
    user=Depends(require_admin),
):
    tag_list = parse_tags_field(tags)
    try:
        metadata_dict = parse_metadata_field(metadata)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )
    normalized_metadata, error = knowledge.validate_document_metadata(metadata_dict)
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    try:
        target, error = knowledge.save_upload_file(file)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )

    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    relative_path = str(target.relative_to(knowledge.PROJECT_ROOT))
    document_id = target.name
    job_id = enqueue_index_job(
        background_tasks,
        path=relative_path,
        document_id=document_id,
        notes=notes,
        category=category,
        tags=tag_list,
        use_original_name=True,
        metadata=normalized_metadata,
    )
    add_admin_audit_event(
        user,
        "knowledge.upload",
        "knowledge_document",
        target_id=document_id,
        details={
            "job_id": job_id,
            "path": relative_path,
            "file_name": file.filename,
            "category": category,
            "tags": tag_list or [],
        },
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=IndexJobResponse(
            job_id=job_id,
            status="queued",
            document_id=document_id,
            path=relative_path,
            result=None,
            error=None,
        ).model_dump(),
    )


@router.get("/knowledge/index-jobs/{job_id}", response_model=IndexJobResponse, dependencies=[Depends(require_admin)])
def knowledge_index_job(job_id: str):
    job = get_index_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Index job not found.",
        )
    return IndexJobResponse(
        job_id=job["id"],
        status=job["status"],
        document_id=job.get("document_id"),
        path=job.get("path"),
        result=job.get("result"),
        error=job.get("error"),
        acknowledged_at=job.get("acknowledged_at"),
    )


@router.post("/knowledge/index-jobs/acknowledge-failed", dependencies=[Depends(require_admin)])
def acknowledge_knowledge_index_failures(payload: AcknowledgeIndexJobsRequest):
    acknowledged = acknowledge_failed_index_jobs(payload.job_ids)
    return {
        "acknowledged_count": len(acknowledged),
        "acknowledged_job_ids": acknowledged,
    }


@router.get("/knowledge/documents", dependencies=[Depends(require_admin)])
def knowledge_documents():
    docs = vector_store.list_documents()
    # 为每个文档获取元数据
    enhanced_docs = []
    for doc in docs:
        doc_info = {"document_id": doc} if isinstance(doc, str) else doc
        doc_id = doc_info.get("document_id") or doc
        metadata = vector_store.get_document_metadata(doc_id)
        source_path = knowledge.source_path_from_metadata(doc_id, metadata)
        if metadata:
            doc_info["metadata"] = metadata
            doc_info["file_name"] = metadata.get("file_name") or doc_id
            doc_info["source_path"] = metadata.get("source_path")
            doc_info["file_ext"] = metadata.get("file_ext")
            doc_info["file_size"] = metadata.get("file_size")
            doc_info["category"] = metadata.get("category")
            doc_info["tags"] = metadata.get("tags") or []
            doc_info["indexed_at"] = metadata.get("indexed_at")
            doc_info["department"] = metadata.get("department")
            doc_info["doc_type"] = metadata.get("doc_type")
            doc_info["sensitivity"] = metadata.get("sensitivity")
            doc_info["version"] = metadata.get("version")
            doc_info["owner"] = metadata.get("owner")
            doc_info["effective_date"] = metadata.get("effective_date")
            doc_info["expiry_date"] = metadata.get("expiry_date")
        else:
            doc_info["file_name"] = doc_id
            doc_info["tags"] = []
        doc_info["source_exists"] = source_path is not None
        enhanced_docs.append(doc_info)
    
    return {"documents": enhanced_docs}


@router.delete("/knowledge/documents/{document_id}", dependencies=[Depends(require_admin)])
def delete_knowledge_document(document_id: str, user=Depends(require_admin)):
    metadata = vector_store.get_document_metadata(document_id)
    deleted_source_path = None
    vector_store.delete_document(document_id)
    try:
        deleted_source_path = knowledge.delete_uploaded_source_file(document_id, metadata)
    except OSError as error:
        log_event(
            logger,
            40,
            "knowledge_source_delete_failed",
            document_id=document_id,
            error=str(error),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Knowledge document was removed from indexes, but source file deletion failed: {error}",
        )
    result = {
        "deleted": True,
        "document_id": document_id,
        "source_deleted": deleted_source_path is not None,
        "source_path": deleted_source_path,
    }
    add_admin_audit_event(
        user,
        "knowledge.delete",
        "knowledge_document",
        target_id=document_id,
        details={
            "source_deleted": result["source_deleted"],
            "source_path": deleted_source_path,
        },
    )
    return result


@router.post("/knowledge/reindex", dependencies=[Depends(require_admin)])
def reindex_all_knowledge_documents(background_tasks: BackgroundTasks, user=Depends(require_admin)):
    queued_jobs = []
    skipped_documents = []

    for doc in vector_store.list_documents():
        doc_info = {"document_id": doc} if isinstance(doc, str) else doc
        document_id = doc_info.get("document_id")
        if not document_id:
            continue

        metadata = vector_store.get_document_metadata(document_id) or {}
        source_path = knowledge.source_path_from_metadata(document_id, metadata)
        if source_path is None:
            skipped_documents.append(document_id)
            continue

        try:
            relative_path = str(source_path.relative_to(knowledge.PROJECT_ROOT))
        except ValueError:
            relative_path = str(source_path)
        job_id = enqueue_index_job(
            background_tasks,
            path=relative_path,
            document_id=document_id,
            notes=metadata.get("user_notes"),
            category=metadata.get("category"),
            tags=metadata.get("tags") if isinstance(metadata.get("tags"), list) else None,
            use_original_name=True,
            metadata=metadata,
            force_reindex=True,
        )
        queued_jobs.append({
            "job_id": job_id,
            "document_id": document_id,
            "path": relative_path,
        })

    content = {
        "queued_count": len(queued_jobs),
        "skipped_count": len(skipped_documents),
        "jobs": queued_jobs,
        "skipped_documents": skipped_documents,
    }
    add_admin_audit_event(
        user,
        "knowledge.reindex_all",
        "knowledge_collection",
        details={
            "queued_count": content["queued_count"],
            "skipped_count": content["skipped_count"],
            "document_ids": [job["document_id"] for job in queued_jobs],
            "skipped_documents": skipped_documents,
        },
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=content,
    )


@router.get("/knowledge/sources", dependencies=[Depends(require_admin)])
def list_knowledge_sources():
    return {"sources": knowledge_sources.list_sources()}


@router.post("/knowledge/sources/{source_id}/sync", dependencies=[Depends(require_admin)])
def sync_knowledge_source(source_id: int, background_tasks: BackgroundTasks, user=Depends(require_admin)):
    def enqueue_source_index(**kwargs):
        return enqueue_index_job(background_tasks, **kwargs)

    result, error = knowledge_sources.sync_source(source_id, enqueue_source_index)
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )
    add_admin_audit_event(
        user,
        "knowledge_source.sync",
        "knowledge_source",
        target_id=source_id,
        details={
            "queued_count": result.get("queued_count"),
            "unchanged_count": result.get("unchanged_count"),
            "missing_count": result.get("missing_count"),
            "skipped_count": result.get("skipped_count"),
            "removed_index_count": result.get("removed_index_count"),
        },
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=result,
    )


@router.delete("/knowledge/sources/missing-files", dependencies=[Depends(require_admin)])
def clear_missing_knowledge_source_files(user=Depends(require_admin)):
    deleted_count = delete_missing_knowledge_source_files()
    add_admin_audit_event(
        user,
        "knowledge_source.clear_missing_files",
        "knowledge_source_file",
        details={"deleted_count": deleted_count},
    )
    return {"deleted_count": deleted_count}


@router.post("/knowledge/documents/deduplicate", dependencies=[Depends(require_admin)])
def deduplicate_knowledge_documents(user=Depends(require_admin)):
    result = vector_store.deduplicate_documents_by_content_hash(
        reassign_document=reassign_knowledge_source_files,
    )
    add_admin_audit_event(
        user,
        "knowledge.deduplicate",
        "knowledge_document",
        details={
            "duplicate_group_count": result["duplicate_group_count"],
            "removed_count": result["removed_count"],
            "removed_documents": result["removed_documents"],
        },
    )
    return result


@router.post("/knowledge/search")
def search_knowledge(request: SearchKnowledgeRequest, user=Depends(require_admin)):
    scope_token = model_usage.set_usage_scope("knowledge_search")
    top_k = max(1, min(request.top_k, tools.MAX_KNOWLEDGE_RESULTS))
    try:
        start = time.perf_counter()
        retrieval_payload = search_knowledge_payload(
            request.query,
            top_k=top_k,
            min_score=request.min_score,
            category=request.category,
            tags=request.tags,
            file_extensions=request.file_extensions,
            departments=user_knowledge_departments(user),
        )
        kept_results = retrieval_payload["kept_results"]
        log_event(
            logger,
            20,
            "knowledge_search_completed",
            top_k=top_k,
            min_score=request.min_score,
            category=request.category,
            tags=request.tags or [],
            file_extensions=request.file_extensions or [],
            result_count=len(kept_results),
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
        )

        result_sources = [search_result_to_source(result) for result in kept_results]
        add_knowledge_access_audit(
            user,
            "knowledge_search",
            request.query,
            result_sources,
            access_stats=retrieval_payload.get("access_stats"),
        )
        evidence_status = "supported" if len(result_sources) >= MIN_EVIDENCE_SOURCES else "insufficient"
        return {
            "results": result_sources,
            "evidence_status": evidence_status,
            "confidence": "high" if evidence_status == "supported" else "none",
            "access_stats": retrieval_payload.get("access_stats", {}),
        }
    finally:
        model_usage.reset_usage_scope(scope_token)
