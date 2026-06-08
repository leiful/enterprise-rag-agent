from __future__ import annotations

from pathlib import Path

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import Field

import vector_store
from config import HYBRID_BM25_WEIGHT, HYBRID_VECTOR_WEIGHT
from knowledge_access import (
    can_access_document,
    document_lifecycle_status,
    document_version_group,
    parse_metadata_datetime,
    parse_version_sort_key,
)


class KnowledgeBaseRetriever(BaseRetriever):
    top_k: int = Field(default=10)
    bm25_weight: float = Field(default=HYBRID_BM25_WEIGHT)
    vector_weight: float = Field(default=HYBRID_VECTOR_WEIGHT)
    category: str | None = Field(default=None)
    tags: list[str] | None = Field(default=None)
    file_extensions: list[str] | None = Field(default=None)
    departments: list[str] | None = Field(default=None)
    include_inactive: bool = Field(default=False)
    prefer_latest_version: bool = Field(default=True)
    last_access_stats: dict = Field(default_factory=dict)

    def _get_relevant_documents(self, query: str, *, run_manager=None):
        results = vector_store.hybrid_search(
            query,
            top_k=self.top_k,
            bm25_weight=self.bm25_weight,
            vector_weight=self.vector_weight,
        )

        stats = {
            "query": query,
            "candidate_count": len(results),
            "kept_count": 0,
            "file_extension_filtered_count": 0,
            "metadata_filtered_count": 0,
            "access_filtered_count": 0,
            "inactive_filtered_count": 0,
            "older_version_filtered_count": 0,
        }
        kept_items = []
        for result in results:
            if self.file_extensions:
                ext = Path(result.document_id).suffix.lower()
                if ext not in [item.lower() for item in self.file_extensions]:
                    stats["file_extension_filtered_count"] += 1
                    continue

            metadata = vector_store.get_document_metadata(result.document_id) or {}
            lifecycle_status = document_lifecycle_status(metadata)
            if not self.include_inactive and lifecycle_status != "active":
                stats["inactive_filtered_count"] += 1
                continue

            if self.category or self.tags or self.departments is not None:
                if not metadata and (self.category or self.tags):
                    stats["metadata_filtered_count"] += 1
                    continue
                if self.category and metadata.get("category") != self.category:
                    stats["metadata_filtered_count"] += 1
                    continue
                if self.tags:
                    doc_tags = metadata.get("tags", [])
                    if not any(tag in doc_tags for tag in self.tags):
                        stats["metadata_filtered_count"] += 1
                        continue
                if self.departments is not None:
                    if not can_access_document(metadata, self.departments):
                        stats["access_filtered_count"] += 1
                        continue

            result_metadata = {
                "score": result.score,
                "chunk_id": result.chunk_id,
                "document_id": result.document_id,
                "chunk_index": result.chunk_index,
                "lifecycle_status": lifecycle_status,
            }
            result_metadata.update(result.metadata or {})
            kept_items.append(
                {
                    "result": result,
                    "document_metadata": metadata,
                    "document": Document(
                        page_content=result.text,
                        metadata=result_metadata,
                    ),
                }
            )

        if self.prefer_latest_version:
            kept_items = self._filter_older_versions(kept_items, stats)

        kept = [item["document"] for item in kept_items]
        stats["kept_count"] = len(kept)
        self.last_access_stats = stats
        return kept

    def _filter_older_versions(self, kept_items, stats):
        latest_by_group = {}
        for item in kept_items:
            result = item["result"]
            metadata = item["document_metadata"]
            group = document_version_group(result.document_id, metadata)
            sort_key = (
                parse_metadata_datetime(metadata.get("effective_date")) or parse_metadata_datetime(metadata.get("indexed_at")),
                parse_version_sort_key(metadata.get("version")),
                result.score,
            )
            current = latest_by_group.get(group)
            if current is None or sort_key > current["sort_key"]:
                latest_by_group[group] = {"sort_key": sort_key, "document_id": result.document_id}

        filtered_items = []
        for item in kept_items:
            result = item["result"]
            metadata = item["document_metadata"]
            group = document_version_group(result.document_id, metadata)
            latest_document_id = latest_by_group[group]["document_id"]
            if result.document_id != latest_document_id:
                stats["older_version_filtered_count"] += 1
                continue
            filtered_items.append(item)

        return filtered_items
