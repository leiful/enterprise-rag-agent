<script setup>
defineProps({
  ragEvalSuites: { type: Array, required: true },
  selectedRagEvalSuite: { type: String, required: true },
  selectedRagEvalSuiteInfo: { type: Object, default: null },
  ragEvalRunning: { type: Boolean, required: true },
  ragEvalLoading: { type: Boolean, required: true },
  ragEvalError: { type: String, default: "" },
  ragEval: { type: Object, default: null },
  runRagEval: { type: Function, required: true },
  loadRagEval: { type: Function, required: true },
  formatDate: { type: Function, required: true },
  isRetrievalOnlyReport: { type: Function, required: true },
  formatPercent: { type: Function, required: true },
  failureReasonEntries: { type: Function, required: true },
  formatFailureReason: { type: Function, required: true },
  evalRowStatus: { type: Function, required: true },
  evalRowTitle: { type: Function, required: true },
  evalRowStatusLabel: { type: Function, required: true },
  formatSourceName: { type: Function, required: true },
  formatScore: { type: Function, required: true },
});

const emit = defineEmits(["update:selectedRagEvalSuite"]);
</script>

<template>
  <div class="audit-header">
    <div>
      <h3>Answer Quality</h3>
      <p>{{ selectedRagEvalSuiteInfo?.description || "Latest benchmark report and retrieval quality signals." }}</p>
    </div>
    <div class="eval-actions">
      <select
        v-if="ragEvalSuites.length > 1"
        :value="selectedRagEvalSuite"
        :disabled="ragEvalRunning"
        title="Choose which evaluation suite Run test will execute"
        @change="emit('update:selectedRagEvalSuite', $event.target.value)"
      >
        <option v-for="suite in ragEvalSuites" :key="suite.id" :value="suite.id">
          {{ suite.name }} - {{ suite.question_count }}
        </option>
      </select>
      <span v-else class="eval-suite-label">
        {{ selectedRagEvalSuiteInfo?.name || "Uploaded PDF Baseline" }}
      </span>
      <button
        class="secondary-button"
        type="button"
        :disabled="ragEvalRunning || ragEvalSuites.length === 0"
        @click="runRagEval"
      >
        {{ ragEvalRunning ? "Running" : "Run test" }}
      </button>
      <button
        class="secondary-button"
        type="button"
        :disabled="ragEvalLoading || ragEvalRunning"
        @click="loadRagEval"
      >
        Refresh
      </button>
    </div>
  </div>

  <p v-if="ragEvalError" class="error users-error">{{ ragEvalError }}</p>

  <div v-if="ragEval?.available" class="eval-panel">
    <div class="rag-status-summary">
      <span>{{ ragEval.report?.name }}</span>
      <span>{{ formatDate(ragEval.report?.updated_at) }}</span>
      <span>{{ ragEval.summary?.total || 0 }} questions</span>
      <span>{{ isRetrievalOnlyReport(ragEval) ? "retrieval only" : "answer quality" }}</span>
    </div>
    <div class="rag-metric-grid eval-metric-grid">
      <div>
        <strong>{{ formatPercent(ragEval.summary?.recall_at_k) }}</strong>
        <span>Recall@K</span>
      </div>
      <div>
        <strong>
          {{
            ragEval.summary?.average_score == null
              ? formatPercent(ragEval.summary?.top1_hit_rate)
              : Number(ragEval.summary.average_score || 0).toFixed(2)
          }}
        </strong>
        <span>{{ ragEval.summary?.average_score == null ? "Top-1" : "Avg score" }}</span>
      </div>
      <div>
        <strong>{{ formatPercent(ragEval.summary?.evidence_hit_rate) }}</strong>
        <span>evidence</span>
      </div>
      <div>
        <strong>{{ formatPercent(ragEval.summary?.citation_rate) }}</strong>
        <span>citation</span>
      </div>
      <div>
        <strong>{{ formatPercent(ragEval.summary?.abstention_accuracy) }}</strong>
        <span>abstention</span>
      </div>
      <div>
        <strong>{{ ragEval.summary?.failed_count || 0 }}</strong>
        <span>needs review</span>
      </div>
    </div>
    <div v-if="failureReasonEntries(ragEval.summary).length" class="failure-reason-row">
      <span v-for="item in failureReasonEntries(ragEval.summary)" :key="item.reason">
        {{ formatFailureReason(item.reason) }}: {{ item.count }}
      </span>
    </div>
    <div v-if="ragEval.rows?.length" class="eval-result-list">
      <article
        v-for="row in ragEval.rows"
        :key="row.id || row.question"
        class="eval-result-item"
        :class="evalRowStatus(row)"
      >
        <div class="eval-result-header">
          <strong>{{ evalRowTitle(row) }}</strong>
          <span>{{ evalRowStatusLabel(row) }}</span>
        </div>
        <p>{{ row.question }}</p>
        <div class="eval-result-meta">
          <span>expected {{ row.expected_docs || "no source" }}</span>
          <span>top {{ formatSourceName(row.top_document) || "none" }}</span>
          <span>score {{ formatScore(row.top_score) }}</span>
          <span v-if="row.expected_rank">rank {{ row.expected_rank }}</span>
          <span v-if="row.evidence_terms_score !== undefined && row.evidence_terms_score !== ''">
            evidence {{ Number(row.evidence_terms_score || 0).toFixed(2) }}
          </span>
          <span v-if="row.failure_reasons?.length">
            {{ row.failure_reasons.map(formatFailureReason).join(", ") }}
          </span>
        </div>
        <p v-if="row.answer" class="eval-answer-preview">{{ row.answer }}</p>
      </article>
    </div>
    <div v-if="ragEval.failed_rows?.length" class="eval-failure-list">
      <h4>Needs review</h4>
      <article v-for="row in ragEval.failed_rows" :key="row.id || row.question">
        <div class="eval-failure-header">
          <strong>{{ row.id || row.category || "case" }}</strong>
          <span>{{ (row.failure_reasons || []).map(formatFailureReason).join(", ") }}</span>
        </div>
        <p>{{ row.question }}</p>
        <span>
          expected {{ row.expected_docs || "no source" }} | top {{ formatSourceName(row.top_document) || "none" }} | score {{ formatScore(row.top_score) }}
          <template v-if="row.evidence_terms_score !== undefined && row.evidence_terms_score !== ''">
            | evidence {{ Number(row.evidence_terms_score || 0).toFixed(2) }}
          </template>
        </span>
        <p v-if="row.answer" class="eval-answer-preview">{{ row.answer }}</p>
      </article>
    </div>
  </div>
  <p v-else-if="!ragEvalLoading" class="empty-state eval-empty">
    No evaluation report found. Run the RAG evaluation script to populate this panel.
  </p>
</template>
