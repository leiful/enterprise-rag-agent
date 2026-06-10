import { EMPTY_MESSAGE } from "./appConfig";

export function formatStatusCount(counts, key) {
  return Number(counts?.[key] || 0);
}

export function formatRagFeature(value) {
  return value ? "on" : "off";
}

export function formatPercent(value) {
  return `${(Number(value || 0) * 100).toFixed(0)}%`;
}

export function formatNumber(value) {
  return Number(value || 0).toLocaleString();
}

export function formatUsageBucket(value) {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function formatUsageDay(value) {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return date.toLocaleDateString([], { month: "short", day: "numeric" });
}

export function formatUsageTrendBucket(value, period) {
  return period === "today" ? formatUsageBucket(value) : formatUsageDay(value);
}

export function formatUsageTrendAxisBucket(value, period) {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  if (period === "today") {
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  return formatUsageDay(value);
}

export function parseUsageMetadata(row) {
  if (!row?.metadata_json) {
    return {};
  }
  try {
    return JSON.parse(row.metadata_json);
  } catch {
    return {};
  }
}

export function formatUsageEventDetail(row) {
  const metadata = parseUsageMetadata(row);
  return metadata.job_id || metadata.document_id || metadata.path || row.request_id || "";
}

export function formatScopeLabel(scope) {
  const labels = {
    chat: "Chat",
    evaluation: "Tests",
    knowledge_search: "Knowledge search",
    indexing: "Indexing",
    other: "Other",
  };
  return labels[scope] || scope;
}

export function formatOperationLabel(operation) {
  const labels = {
    embedding: "Embedding",
    rerank: "Rerank",
    chat: "Chat",
    chat_stream: "Chat stream",
  };
  return labels[operation] || operation;
}

export function formatFailureReason(reason) {
  const labels = {
    expected_source_missed: "Source mismatch",
    evidence_terms_missing: "Evidence detail check",
    missing_citation: "Citation check",
    expected_terms_missing: "Answer detail check",
    unexpected_source_for_unknown: "Unexpected source",
    unknown_not_abstained: "Abstention check",
    manual_score_below_7: "Manual score below 7",
  };
  return labels[reason] || reason;
}

export function failureReasonEntries(summary) {
  return Object.entries(summary?.failure_reasons || {}).map(([reason, count]) => ({
    reason,
    count,
  }));
}

export function evalRowStatus(row) {
  if (row.strict_failure || row.unexpected_sources || (row.expected_docs && !row.expected_hit)) {
    return "review";
  }
  if (row.expected_hit || row.abstained) {
    return "pass";
  }
  return "neutral";
}

export function evalRowStatusLabel(row) {
  const status = evalRowStatus(row);
  if (status === "pass") {
    return "Pass";
  }
  if (status === "review") {
    return "Check";
  }
  return "No score";
}

export function evalRowTitle(row) {
  return row.id || row.metadata?.id || row.category || "case";
}

export function isRetrievalOnlyReport(report) {
  return Boolean(report?.rows?.length) && report.rows.every((row) => !row.answer);
}

export function feedbackTypeLabel(type) {
  const labels = {
    useful: "Useful",
    not_useful: "Not useful",
    wrong_source: "Wrong source",
    outdated: "Outdated",
    missing_doc: "Missing doc",
  };
  return labels[type] || type;
}

export function formatDepartments(departments) {
  const values = Array.isArray(departments) ? departments.filter(Boolean) : [];
  return values.length ? values.join(", ") : "No departments";
}

export function formatAuditScope(audit) {
  const scope = audit?.scope || {};
  if (scope.is_admin || scope.role === "admin") {
    return "Scope: all departments";
  }
  return `Scope: ${formatDepartments(scope.departments || [])}`;
}

function auditStats(audit) {
  return audit?.access_stats || {};
}

export function auditFilteredCount(audit) {
  return Number(auditStats(audit).access_filtered_count || 0);
}

export function auditInactiveFilteredCount(audit) {
  return Number(auditStats(audit).inactive_filtered_count || 0);
}

export function auditOlderVersionFilteredCount(audit) {
  return Number(auditStats(audit).older_version_filtered_count || 0);
}

export function auditCandidateCount(audit) {
  return Number(auditStats(audit).candidate_count || 0);
}

export function auditKeptCount(audit) {
  return Number(auditStats(audit).kept_count || 0);
}

export function auditSourceDepartment(source) {
  return source?.metadata?.department || source?.department || "Public";
}

export function auditSourceGroups(audit) {
  const groups = new Map();
  for (const source of audit?.sources || []) {
    const documentName = formatSourceName(source.document_id);
    const department = auditSourceDepartment(source);
    const key = `${documentName}::${department}`;
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        documentName,
        department,
        sources: [],
      });
    }
    groups.get(key).sources.push(source);
  }
  return Array.from(groups.values());
}

export function auditChunkLabel(source) {
  const parts = [];
  if (source?.chunk_index !== undefined && source?.chunk_index !== null) {
    parts.push(`chunk ${source.chunk_index}`);
  }
  const pageRange = formatPageRange(source);
  if (pageRange) {
    parts.push(pageRange);
  }
  const structure = formatStructureLocation(source);
  if (structure) {
    parts.push(structure);
  }
  parts.push(`score ${formatScore(source?.score)}`);
  return parts.join(" / ");
}

export function formatScore(score) {
  return Number(score || 0).toFixed(3);
}

export function formatPageRange(item) {
  const pageStart = Number(item?.page_start || item?.metadata?.page_start || 0);
  const pageEnd = Number(item?.page_end || item?.metadata?.page_end || pageStart);
  if (!pageStart) {
    return "";
  }
  if (!pageEnd || pageEnd === pageStart) {
    return `page ${pageStart}`;
  }
  return `pages ${pageStart}-${pageEnd}`;
}

export function itemMetadata(item) {
  return item?.metadata || {};
}

export function formatStructureLocation(item) {
  const metadata = itemMetadata(item);
  if (metadata.section_path) {
    return metadata.section_path;
  }
  if (metadata.section_title) {
    return metadata.section_title;
  }

  const sheetName = metadata.sheet_name;
  const rowStart = metadata.row_start;
  const rowEnd = metadata.row_end || rowStart;
  if (sheetName && rowStart) {
    return rowEnd && rowEnd !== rowStart
      ? `${sheetName} rows ${rowStart}-${rowEnd}`
      : `${sheetName} row ${rowStart}`;
  }
  if (sheetName) {
    return sheetName;
  }
  return "";
}

export function formatLifecycle(document) {
  const now = new Date();
  const effectiveAt = document?.effective_date ? new Date(document.effective_date) : null;
  const expiryAt = document?.expiry_date ? new Date(document.expiry_date) : null;
  if (effectiveAt && !Number.isNaN(effectiveAt.getTime()) && effectiveAt > now) {
    return "not yet effective";
  }
  if (expiryAt && !Number.isNaN(expiryAt.getTime()) && expiryAt < now) {
    return "expired";
  }
  return "active";
}

export function lifecycleClass(document) {
  return {
    active: formatLifecycle(document) === "active",
    inactive: formatLifecycle(document) !== "active",
  };
}

export function formatSourceName(documentId) {
  const value = String(documentId || "").trim();
  if (!value) {
    return "Unknown source";
  }
  if (value.includes("__")) {
    return value.split("__").filter(Boolean).pop() || value;
  }
  return value;
}

export function formatFileSize(bytes) {
  const value = Number(bytes || 0);
  if (!value) {
    return "0 B";
  }
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / 1024 / 1024).toFixed(2)} MB`;
}

export function decodeSourcesHeader(value) {
  if (!value) {
    return [];
  }

  try {
    const bytes = Uint8Array.from(atob(value), (char) => char.charCodeAt(0));
    const decoded = new TextDecoder().decode(bytes);
    return JSON.parse(decoded);
  } catch {
    return [];
  }
}

export function hasSources(message) {
  return Array.isArray(message.sources);
}

export function normalizeMessages(rawMessages) {
  const normalized = (rawMessages || []).map((message) => ({
    id: message.id,
    role: message.role,
    content: message.content,
    sources: message.sources,
    created_at: message.created_at,
    feedbackSent: message.feedbackSent,
    feedbackError: message.feedbackError,
  }));

  return normalized.length > 0 ? normalized : [EMPTY_MESSAGE];
}
