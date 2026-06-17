<script setup>
import { computed, ref, watch } from "vue";
import { PAGE_SIZE } from "../appConfig.js";
import { paginateItems, totalPages } from "../pagination.js";
import KnowledgeEvaluationPanel from "./KnowledgeEvaluationPanel.vue";

const props = defineProps({
  knowledgeLoading: { type: Boolean, required: true },
  knowledgeDocuments: { type: Array, required: true },
  hasEnabledKnowledgeSources: { type: Boolean, required: true },
  ragStatus: { type: Object, default: null },
  ragStatusError: { type: String, default: "" },
  failedIndexJobsExpanded: { type: Boolean, required: true },
  acknowledgingFailedJobs: { type: Boolean, required: true },
  knowledgeTab: { type: String, required: true },
  selectedKnowledgeFile: { type: Object, default: null },
  knowledgeNotes: { type: String, required: true },
  knowledgeDepartment: { type: String, required: true },
  departments: { type: Array, required: true },
  knowledgeError: { type: String, default: "" },
  knowledgeIndexJob: { type: Object, default: null },
  knowledgeSearchQuery: { type: String, required: true },
  knowledgeSearchLoading: { type: Boolean, required: true },
  knowledgeSearchError: { type: String, default: "" },
  knowledgeSearchResults: { type: Array, required: true },
  ragEvalSuites: { type: Array, required: true },
  selectedRagEvalSuite: { type: String, required: true },
  selectedRagEvalSuiteInfo: { type: Object, default: null },
  ragEvalRunning: { type: Boolean, required: true },
  ragEvalLoading: { type: Boolean, required: true },
  ragEvalError: { type: String, default: "" },
  ragEval: { type: Object, default: null },
  syncEnabledKnowledgeSources: { type: Function, required: true },
  clearMissingKnowledgeFiles: { type: Function, required: true },
  formatStatusCount: { type: Function, required: true },
  ragStatusClass: { type: Function, required: true },
  formatRagFeature: { type: Function, required: true },
  acknowledgeFailedIndexJobs: { type: Function, required: true },
  formatDate: { type: Function, required: true },
  setKnowledgeTab: { type: Function, required: true },
  uploadKnowledgeFile: { type: Function, required: true },
  onKnowledgeFileChange: { type: Function, required: true },
  searchKnowledge: { type: Function, required: true },
  defaultKnowledgeMinScore: { type: Function, required: true },
  formatSourceName: { type: Function, required: true },
  formatPageRange: { type: Function, required: true },
  formatStructureLocation: { type: Function, required: true },
  formatScore: { type: Function, required: true },
  formatFileSize: { type: Function, required: true },
  lifecycleClass: { type: Function, required: true },
  formatLifecycle: { type: Function, required: true },
  deleteKnowledgeDocument: { type: Function, required: true },
  runRagEval: { type: Function, required: true },
  loadRagEval: { type: Function, required: true },
  isRetrievalOnlyReport: { type: Function, required: true },
  formatPercent: { type: Function, required: true },
  failureReasonEntries: { type: Function, required: true },
  formatFailureReason: { type: Function, required: true },
  evalRowStatus: { type: Function, required: true },
  evalRowTitle: { type: Function, required: true },
  evalRowStatusLabel: { type: Function, required: true },
});

const emit = defineEmits([
  "update:failedIndexJobsExpanded",
  "update:selectedKnowledgeFile",
  "update:knowledgeNotes",
  "update:knowledgeDepartment",
  "update:knowledgeSearchQuery",
  "update:selectedRagEvalSuite",
]);

const fileInput = ref(null);

function chooseFile() {
  fileInput.value?.click();
}

function handleFileChange(event) {
  props.onKnowledgeFileChange(event);
  emit("update:selectedKnowledgeFile", event.target.files?.[0] || null);
}

watch(
  () => props.selectedKnowledgeFile,
  (file) => {
    if (!file && fileInput.value) {
      fileInput.value.value = "";
    }
  },
);

const documentPage = ref(1);
const documentSearch = ref("");
const documentDepartment = ref("");

const filteredKnowledgeDocuments = computed(() => {
  const search = documentSearch.value.trim().toLowerCase();
  const department = documentDepartment.value;
  if (!search && !department) {
    return props.knowledgeDocuments;
  }

  return props.knowledgeDocuments.filter((document) => {
    const name = (document.file_name || document.document_id || "").toLowerCase();
    const path = (document.source_path || "").toLowerCase();
    const dept = (document.department || "").toLowerCase();
    const searchMatch =
      !search || name.includes(search) || path.includes(search) || dept.includes(search);
    const departmentMatch = !department || dept === department.toLowerCase();
    return searchMatch && departmentMatch;
  });
});

const totalDocumentPages = computed(() => totalPages(filteredKnowledgeDocuments.value.length, PAGE_SIZE));
const pagedKnowledgeDocuments = computed(() => paginateItems(filteredKnowledgeDocuments.value, documentPage.value, PAGE_SIZE));

watch([documentSearch, documentDepartment, () => props.knowledgeDocuments], () => {
  documentPage.value = 1;
});
</script>

<template>
  <div class="knowledge-column">
    <section class="knowledge-section">
      <div class="section-header">
        <div>
          <h2>Knowledge</h2>
          <p>Upload documents into vector search. Max file size: 50MB.</p>
        </div>
        <div class="header-actions">
          <button
            class="secondary-button"
            type="button"
            :disabled="knowledgeLoading || !hasEnabledKnowledgeSources"
            @click="syncEnabledKnowledgeSources"
          >
            Sync now
          </button>
          <button
            v-if="formatStatusCount(ragStatus?.sources?.file_status_counts, 'missing') > 0"
            class="secondary-button"
            type="button"
            :disabled="knowledgeLoading"
            @click="clearMissingKnowledgeFiles"
          >
            Clear missing
          </button>
        </div>
      </div>

      <p v-if="ragStatusError" class="error knowledge-error">{{ ragStatusError }}</p>
      <div v-if="ragStatus" class="rag-status-panel">
        <div class="rag-status-summary">
          <span class="rag-status-badge" :class="ragStatusClass()">{{ ragStatus.status }}</span>
          <span>{{ ragStatus.documents?.count || 0 }} docs</span>
          <span>{{ ragStatus.documents?.chunk_count || 0 }} chunks</span>
          <span>{{ ragStatus.sources?.enabled_count || 0 }} active sources</span>
        </div>
        <div class="rag-metric-grid">
          <button
            class="metric-button"
            type="button"
            :disabled="!ragStatus.index_jobs?.recent_failed?.length"
            @click="emit('update:failedIndexJobsExpanded', !failedIndexJobsExpanded)"
          >
            <strong>
              {{ ragStatus.index_jobs?.failed_unacknowledged_count || 0 }}
              <template v-if="formatStatusCount(ragStatus.index_jobs?.status_counts, 'failed')">
                / {{ formatStatusCount(ragStatus.index_jobs?.status_counts, "failed") }}
              </template>
            </strong>
            <span>failed jobs</span>
          </button>
          <div>
            <strong>{{ formatStatusCount(ragStatus.sources?.file_status_counts, "missing") }}</strong>
            <span>missing files</span>
          </div>
          <div>
            <strong>{{ ragStatus.retrieval?.bm25_total_docs || 0 }}</strong>
            <span>BM25 docs</span>
          </div>
          <div>
            <strong>{{ ragStatus.audit?.event_count || 0 }}</strong>
            <span>audit events</span>
          </div>
          <div>
            <strong>{{ ragStatus.retrieval?.default_top_k || 0 }}</strong>
            <span>default top-k</span>
          </div>
          <div>
            <strong>{{ Number(ragStatus.retrieval?.default_min_score || 0).toFixed(2) }}</strong>
            <span>min score</span>
          </div>
        </div>
        <div class="rag-feature-row">
          <span>rewrite {{ formatRagFeature(ragStatus.retrieval?.query_rewrite_enabled) }}</span>
          <span>multi-query {{ formatRagFeature(ragStatus.retrieval?.multi_query_enabled) }}</span>
          <span>rerank {{ formatRagFeature(ragStatus.retrieval?.rerank_enabled) }}</span>
          <span>recall {{ ragStatus.retrieval?.recall_k || 0 }}</span>
        </div>
        <div
          v-if="failedIndexJobsExpanded && ragStatus.index_jobs?.recent_failed?.length"
          class="failed-job-panel"
        >
          <div class="failed-job-header">
            <strong>Failed index jobs</strong>
            <button
              class="secondary-button"
              type="button"
              :disabled="acknowledgingFailedJobs || !ragStatus.index_jobs?.failed_unacknowledged_count"
              @click="acknowledgeFailedIndexJobs()"
            >
              Acknowledge
            </button>
          </div>
          <article
            v-for="job in ragStatus.index_jobs.recent_failed"
            :key="job.id"
            class="failed-job-item"
            :class="{ acknowledged: job.acknowledged_at }"
          >
            <div>
              <strong>{{ job.document_id || job.path || job.id }}</strong>
              <span>{{ job.acknowledged_at ? "acknowledged" : "unacknowledged" }}</span>
            </div>
            <p>{{ job.error || "Unknown error" }}</p>
            <small>{{ formatDate(job.updated_at || job.created_at) }}</small>
          </article>
        </div>
        <ul v-if="ragStatus.issues?.length" class="rag-issue-list">
          <li v-for="issue in ragStatus.issues" :key="issue.name">{{ issue.message }}</li>
        </ul>
      </div>

      <div class="knowledge-tab-actions">
        <div class="operations-tabs" role="tablist" aria-label="Knowledge sections">
          <button
            type="button"
            :class="{ active: knowledgeTab === 'documents' }"
            @click="setKnowledgeTab('documents')"
          >
            Documents
          </button>
          <button
            type="button"
            :class="{ active: knowledgeTab === 'search' }"
            @click="setKnowledgeTab('search')"
          >
            Search test
          </button>
          <button
            type="button"
            :class="{ active: knowledgeTab === 'evaluation' }"
            @click="setKnowledgeTab('evaluation')"
          >
            Answer Quality
          </button>
        </div>
      </div>

      <template v-if="knowledgeTab === 'documents'">
        <form class="index-form" @submit.prevent="uploadKnowledgeFile">
          <input
            ref="fileInput"
            class="hidden-file-input"
            type="file"
            accept=".md,.pdf,.docx,.csv,.xlsx,.xls,text/markdown,application/pdf"
            @change="handleFileChange"
          />
          <label class="notes-field">
            <span>Notes</span>
            <textarea
              :value="knowledgeNotes"
              rows="1"
              placeholder="Optional context for this document"
              @input="emit('update:knowledgeNotes', $event.target.value)"
            />
          </label>
          <label>
            <span>Department</span>
            <select
              :value="knowledgeDepartment"
              @change="emit('update:knowledgeDepartment', $event.target.value)"
            >
              <option value="">Public</option>
              <option v-for="department in departments" :key="department.id" :value="department.name">
                {{ department.name }}
              </option>
            </select>
          </label>
          <div class="file-row">
            <div class="selected-file">
              <strong>{{ selectedKnowledgeFile ? selectedKnowledgeFile.name : "No file selected" }}</strong>
              <span v-if="selectedKnowledgeFile">
                {{ (selectedKnowledgeFile.size / 1024 / 1024).toFixed(2) }} MB
              </span>
            </div>
            <button class="secondary-button file-button" type="button" @click="chooseFile">
              Browse
            </button>
            <button type="submit" :disabled="knowledgeLoading || !selectedKnowledgeFile">
              {{ knowledgeLoading ? "Uploading" : "Upload" }}
            </button>
          </div>
        </form>

        <p v-if="knowledgeError" class="error knowledge-error">{{ knowledgeError }}</p>
        <p v-if="knowledgeIndexJob && knowledgeIndexJob.deduplicated" class="info knowledge-status">
          ℹ️ This file already exists with the same content. Using existing document instead of creating a duplicate.
          <br>
          <small>Document ID: {{ knowledgeIndexJob.duplicate_of }}</small>
        </p>
        <p v-else-if="knowledgeIndexJob && knowledgeIndexJob.status !== 'completed'" class="knowledge-status">
          {{
            knowledgeIndexJob.status === "failed"
              ? `Index failed: ${knowledgeIndexJob.error || "unknown error"}`
              : `Index job ${knowledgeIndexJob.status}: ${knowledgeIndexJob.document_id || knowledgeIndexJob.path || knowledgeIndexJob.job_id}`
          }}
        </p>

        <div class="document-filters">
          <label>
            <span>Document list search</span>
            <input
              v-model="documentSearch"
              placeholder="Search by file name, path, or department"
            />
          </label>
          <label>
            <span>Department</span>
            <select v-model="documentDepartment">
              <option value="">All</option>
              <option
                v-for="department in departments"
                :key="department.id"
                :value="department.name"
              >
                {{ department.name }}
              </option>
            </select>
          </label>
        </div>

        <div class="document-list">
          <article
            v-for="document in pagedKnowledgeDocuments"
            :key="document.document_id"
            class="document-item"
          >
            <div>
              <h3>{{ document.file_name || document.document_id }}</h3>
              <p>
                {{ document.chunk_count }} chunks
                <span v-if="document.updated_at"> / {{ formatDate(document.updated_at) }}</span>
              </p>
              <p class="document-meta">
                <span v-if="document.file_ext">{{ document.file_ext }}</span>
                <span v-if="document.file_size">{{ formatFileSize(document.file_size) }}</span>
                <span :class="document.source_exists ? 'source-ok' : 'source-missing'">
                  {{ document.source_exists ? "source saved" : "source missing" }}
                </span>
                <span :class="lifecycleClass(document)">{{ formatLifecycle(document) }}</span>
              </p>
              <p v-if="document.source_path" class="document-path">{{ document.source_path }}</p>
              <p
                v-if="document.department || document.version || document.sensitivity || document.owner || document.effective_date || document.expiry_date"
                class="document-department"
              >
                <span v-if="document.department">{{ document.department }}</span>
                <span v-if="document.version">version {{ document.version }}</span>
                <span v-if="document.sensitivity">{{ document.sensitivity }}</span>
                <span v-if="document.owner">owner {{ document.owner }}</span>
                <span v-if="document.effective_date">effective {{ document.effective_date }}</span>
                <span v-if="document.expiry_date">expires {{ document.expiry_date }}</span>
              </p>
              <p v-if="document.notes" class="document-notes">{{ document.notes }}</p>
            </div>
            <div class="document-actions">
              <button
                class="danger-button"
                type="button"
                :disabled="knowledgeLoading"
                @click="deleteKnowledgeDocument(document.document_id)"
              >
                Delete
              </button>
            </div>
          </article>

          <p v-if="filteredKnowledgeDocuments.length === 0" class="empty-state">No indexed documents.</p>
        </div>

        <div v-if="totalDocumentPages > 1" class="document-pagination">
          <button
            type="button"
            class="secondary-button"
            :disabled="documentPage === 1"
            @click="documentPage = Math.max(1, documentPage - 1)"
          >
            Previous
          </button>
          <span>
            Page {{ documentPage }} / {{ totalDocumentPages }}
            · {{ filteredKnowledgeDocuments.length }} document(s)
          </span>
          <button
            type="button"
            class="secondary-button"
            :disabled="documentPage >= totalDocumentPages"
            @click="documentPage = Math.min(totalDocumentPages, documentPage + 1)"
          >
            Next
          </button>
        </div>
      </template>

      <template v-else-if="knowledgeTab === 'search'">
        <form class="knowledge-search-form" @submit.prevent="searchKnowledge">
          <label>
            <span>Search test</span>
            <input
              :value="knowledgeSearchQuery"
              placeholder="Test a question against indexed knowledge"
              @input="emit('update:knowledgeSearchQuery', $event.target.value)"
            />
          </label>
          <button type="submit" :disabled="knowledgeSearchLoading || !knowledgeSearchQuery.trim()">
            {{ knowledgeSearchLoading ? "Searching" : "Search" }}
          </button>
        </form>

        <p v-if="knowledgeSearchError" class="error knowledge-error">{{ knowledgeSearchError }}</p>

        <div v-if="knowledgeSearchResults.length" class="search-result-list">
          <article
            v-for="result in knowledgeSearchResults"
            :key="result.chunk_id"
            class="search-result-item"
          >
            <div class="search-result-meta">
              <strong :title="result.document_id">{{ formatSourceName(result.document_id) }}</strong>
              <span>#{{ result.chunk_index }}</span>
              <span v-if="formatPageRange(result)">{{ formatPageRange(result) }}</span>
              <span v-if="formatStructureLocation(result)">{{ formatStructureLocation(result) }}</span>
              <span v-if="result.metadata?.lifecycle_status">{{ result.metadata.lifecycle_status }}</span>
              <span v-if="result.metadata?.version">v{{ result.metadata.version }}</span>
              <span>score {{ formatScore(result.score) }}</span>
            </div>
            <p>{{ result.text }}</p>
          </article>
        </div>

        <p
          v-else-if="knowledgeSearchQuery.trim() && !knowledgeSearchLoading && !knowledgeSearchError"
          class="empty-state search-empty"
        >
          No matching chunks above score {{ defaultKnowledgeMinScore().toFixed(2) }}.
        </p>
      </template>

      <template v-else>
        <KnowledgeEvaluationPanel
          :rag-eval-suites="ragEvalSuites"
          :selected-rag-eval-suite="selectedRagEvalSuite"
          :selected-rag-eval-suite-info="selectedRagEvalSuiteInfo"
          :rag-eval-running="ragEvalRunning"
          :rag-eval-loading="ragEvalLoading"
          :rag-eval-error="ragEvalError"
          :rag-eval="ragEval"
          :run-rag-eval="runRagEval"
          :load-rag-eval="loadRagEval"
          :format-date="formatDate"
          :is-retrieval-only-report="isRetrievalOnlyReport"
          :format-percent="formatPercent"
          :failure-reason-entries="failureReasonEntries"
          :format-failure-reason="formatFailureReason"
          :eval-row-status="evalRowStatus"
          :eval-row-title="evalRowTitle"
          :eval-row-status-label="evalRowStatusLabel"
          :format-source-name="formatSourceName"
          :format-score="formatScore"
          @update:selected-rag-eval-suite="emit('update:selectedRagEvalSuite', $event)"
        />
      </template>
    </section>
  </div>
</template>
