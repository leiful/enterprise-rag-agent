<script setup>
import { reactive } from "vue";

defineProps({
  operationsView: { type: String, required: true },
  operationsTab: { type: String, required: true },
  feedbackLoading: { type: Boolean, required: true },
  feedbackError: { type: String, default: "" },
  selectedFeedbackType: { type: String, default: "" },
  ragFeedbackSummary: { type: Object, default: null },
  ragFeedback: { type: Array, required: true },
  filteredRagFeedback: { type: Array, required: true },
  pagedRagFeedback: { type: Array, required: true },
  pageSize: { type: Number, required: true },
  feedbackPage: { type: Number, required: true },
  feedbackTotalPages: { type: Number, required: true },
  auditLoading: { type: Boolean, required: true },
  auditError: { type: String, default: "" },
  pagedKnowledgeAudits: { type: Array, required: true },
  knowledgeAudits: { type: Array, required: true },
  auditPage: { type: Number, required: true },
  auditTotalPages: { type: Number, required: true },
  missingDocFeedback: { type: Array, required: true },
  pagedMissingDocFeedback: { type: Array, required: true },
  missingDocPage: { type: Number, required: true },
  missingDocTotalPages: { type: Number, required: true },
  openOperationsOverview: { type: Function, required: true },
  openMissingDocManagement: { type: Function, required: true },
  setOperationsTab: { type: Function, required: true },
  loadRagFeedback: { type: Function, required: true },
  setFeedbackPage: { type: Function, required: true },
  setFeedbackTypeFilter: { type: Function, required: true },
  loadKnowledgeAudits: { type: Function, required: true },
  setAuditPage: { type: Function, required: true },
  setMissingDocPage: { type: Function, required: true },
  feedbackTypeLabel: { type: Function, required: true },
  feedbackFilterOptions: { type: Function, required: true },
  formatDate: { type: Function, required: true },
  formatSourceName: { type: Function, required: true },
  formatDepartments: { type: Function, required: true },
  formatAuditScope: { type: Function, required: true },
  auditCandidateCount: { type: Function, required: true },
  auditKeptCount: { type: Function, required: true },
  auditFilteredCount: { type: Function, required: true },
  auditInactiveFilteredCount: { type: Function, required: true },
  auditOlderVersionFilteredCount: { type: Function, required: true },
  auditSourceGroups: { type: Function, required: true },
  auditChunkLabel: { type: Function, required: true },
});

const expandedAnswers = reactive({});

function answerKey(item) {
  return item.id || `${item.conversation_id || "conversation"}-${item.created_at || "time"}`;
}

function isAnswerExpanded(item) {
  return Boolean(expandedAnswers[answerKey(item)]);
}

function toggleAnswer(item) {
  const key = answerKey(item);
  expandedAnswers[key] = !expandedAnswers[key];
}

function shouldShowAnswerToggle(answer) {
  if (!answer) {
    return false;
  }
  return String(answer).length > 140 || String(answer).includes("\n");
}
</script>

<template>
  <div class="users-column">
    <section class="users-section">
      <div class="section-header">
        <div>
          <h2>{{ operationsView === "missing-docs" ? "Missing Doc Management" : "Operations" }}</h2>
          <p>
            {{
              operationsView === "missing-docs"
                ? "Review answer feedback that asks for missing knowledge coverage."
                : "Review answer feedback and knowledge access audit trails."
            }}
          </p>
        </div>
        <button
          v-if="operationsView === 'missing-docs'"
          class="secondary-button"
          type="button"
          @click="openOperationsOverview"
        >
          Back to operations
        </button>
      </div>

      <template v-if="operationsView === 'overview'">
        <div class="operations-tabs" role="tablist" aria-label="Operations sections">
          <button
            type="button"
            :class="{ active: operationsTab === 'feedback' }"
            @click="setOperationsTab('feedback')"
          >
            Answer feedback
          </button>
          <button
            type="button"
            :class="{ active: operationsTab === 'access' }"
            @click="setOperationsTab('access')"
          >
            Knowledge access
          </button>
        </div>

        <template v-if="operationsTab === 'feedback'">
          <div class="audit-header tab-header">
            <div>
              <h3>Answer feedback</h3>
              <p>User feedback grouped into retraining and document-fix signals.</p>
            </div>
            <button
              class="secondary-button"
              type="button"
              :disabled="feedbackLoading"
              @click="loadRagFeedback"
            >
              Refresh
            </button>
          </div>

          <p v-if="feedbackError" class="error users-error">{{ feedbackError }}</p>

          <div class="feedback-panel">
            <div class="rag-metric-grid feedback-metric-grid">
              <button
                v-for="filter in feedbackFilterOptions(ragFeedbackSummary)"
                :key="filter.type"
                class="metric-button"
                type="button"
                :class="{ active: selectedFeedbackType === filter.type || (!selectedFeedbackType && !filter.type) }"
                :disabled="filter.count === 0"
                @click="setFeedbackTypeFilter(filter.type)"
              >
                <strong>{{ filter.count }}</strong>
                <span>{{ filter.label }}</span>
              </button>
            </div>
            <div v-if="selectedFeedbackType" class="feedback-filter-row">
              <span>{{ feedbackTypeLabel(selectedFeedbackType) }} feedback</span>
              <button class="secondary-button" type="button" @click="setFeedbackTypeFilter(selectedFeedbackType)">
                Clear
              </button>
            </div>
            <div v-if="filteredRagFeedback.length" class="feedback-list">
              <article v-for="item in pagedRagFeedback" :key="item.id" class="feedback-item">
                <div class="audit-title">
                  <strong>{{ item.username }}</strong>
                  <span>{{ feedbackTypeLabel(item.feedback_type) }}</span>
                  <span>{{ formatDate(item.created_at) }}</span>
                </div>
                <p>{{ item.query || item.answer || "No question captured." }}</p>
                <p
                  v-if="item.answer"
                  class="feedback-answer-preview"
                  :class="{ expanded: isAnswerExpanded(item) }"
                >
                  {{ item.answer }}
                </p>
                <button
                  v-if="shouldShowAnswerToggle(item.answer)"
                  class="feedback-inline-button"
                  type="button"
                  @click="toggleAnswer(item)"
                >
                  {{ isAnswerExpanded(item) ? "Show less" : "Show more" }}
                </button>
                <p class="audit-meta">
                  <span>{{ item.sources?.length || 0 }} sources</span>
                  <span v-if="item.conversation_id">conversation {{ item.conversation_id }}</span>
                  <span v-if="item.sources?.[0]">{{ formatSourceName(item.sources[0].document_id) }}</span>
                </p>
              </article>
            </div>
            <div v-if="filteredRagFeedback.length > pageSize" class="pagination">
              <button
                class="secondary-button"
                type="button"
                :disabled="feedbackPage <= 1"
                @click="setFeedbackPage(feedbackPage - 1)"
              >
                Previous
              </button>
              <span>Page {{ feedbackPage }} of {{ feedbackTotalPages }}</span>
              <button
                class="secondary-button"
                type="button"
                :disabled="feedbackPage >= feedbackTotalPages"
                @click="setFeedbackPage(feedbackPage + 1)"
              >
                Next
              </button>
            </div>
            <p v-if="filteredRagFeedback.length === 0 && !feedbackLoading" class="empty-state">
              {{ selectedFeedbackType ? `No ${feedbackTypeLabel(selectedFeedbackType)} feedback yet.` : "No answer feedback yet." }}
            </p>
          </div>
        </template>

        <template v-else>
          <div class="audit-header tab-header">
            <div>
              <h3>Knowledge access</h3>
              <p>Recent searches and retrieved knowledge sources.</p>
            </div>
            <button
              class="secondary-button"
              type="button"
              :disabled="auditLoading"
              @click="loadKnowledgeAudits"
            >
              Refresh
            </button>
          </div>

          <p v-if="auditError" class="error users-error">{{ auditError }}</p>

          <div class="audit-list">
            <article v-for="audit in pagedKnowledgeAudits" :key="audit.id" class="audit-item">
              <div>
                <div class="audit-title">
                  <strong>{{ audit.username }}</strong>
                  <span>{{ audit.action }}</span>
                  <span>{{ formatDate(audit.created_at) }}</span>
                </div>
                <p>{{ audit.query }}</p>
                <p class="audit-meta">
                  <span>{{ audit.source_count }} used sources</span>
                  <span>{{ formatDepartments(audit.departments) }}</span>
                  <span>{{ formatAuditScope(audit) }}</span>
                  <span>{{ auditCandidateCount(audit) }} recalled</span>
                  <span>{{ auditKeptCount(audit) }} permission-visible</span>
                  <span>{{ auditFilteredCount(audit) }} permission-filtered</span>
                  <span>{{ auditInactiveFilteredCount(audit) }} inactive-filtered</span>
                  <span>{{ auditOlderVersionFilteredCount(audit) }} older-version-filtered</span>
                </p>
                <div v-if="audit.sources?.length" class="audit-source-list">
                  <details
                    v-for="group in auditSourceGroups(audit)"
                    :key="group.key"
                    class="audit-source-group"
                  >
                    <summary>
                      <span>{{ group.documentName }}</span>
                      <small>{{ group.department }} / {{ group.sources.length }} chunks</small>
                    </summary>
                    <div class="audit-chunk-list">
                      <article
                        v-for="source in group.sources"
                        :key="source.chunk_id || `${source.document_id}-${source.chunk_index}`"
                        class="audit-chunk"
                      >
                        <div class="audit-chunk-meta">{{ auditChunkLabel(source) }}</div>
                        <p>{{ source.text || "No snippet text recorded." }}</p>
                      </article>
                    </div>
                  </details>
                </div>
              </div>
            </article>

            <p v-if="knowledgeAudits.length === 0 && !auditLoading" class="empty-state">
              No knowledge access records yet.
            </p>
            <div v-if="knowledgeAudits.length > pageSize" class="pagination">
              <button
                class="secondary-button"
                type="button"
                :disabled="auditPage <= 1"
                @click="setAuditPage(auditPage - 1)"
              >
                Previous
              </button>
              <span>Page {{ auditPage }} of {{ auditTotalPages }}</span>
              <button
                class="secondary-button"
                type="button"
                :disabled="auditPage >= auditTotalPages"
                @click="setAuditPage(auditPage + 1)"
              >
                Next
              </button>
            </div>
          </div>
        </template>
      </template>

      <template v-else-if="operationsView === 'missing-docs'">
        <div class="audit-header">
          <div>
            <h3>Missing doc requests</h3>
            <p>Questions users marked as needing new or better source documents.</p>
          </div>
          <button
            class="secondary-button"
            type="button"
            :disabled="feedbackLoading"
            @click="loadRagFeedback"
          >
            Refresh
          </button>
        </div>

        <p v-if="feedbackError" class="error users-error">{{ feedbackError }}</p>

        <div v-if="missingDocFeedback.length" class="feedback-list missing-doc-list">
          <article v-for="item in pagedMissingDocFeedback" :key="item.id" class="feedback-item">
            <div class="audit-title">
              <strong>{{ item.username }}</strong>
              <span>{{ formatDate(item.created_at) }}</span>
            </div>
            <p>{{ item.query || item.answer || "No question captured." }}</p>
            <p
              v-if="item.answer"
              class="feedback-answer-preview"
              :class="{ expanded: isAnswerExpanded(item) }"
            >
              {{ item.answer }}
            </p>
            <button
              v-if="shouldShowAnswerToggle(item.answer)"
              class="feedback-inline-button"
              type="button"
              @click="toggleAnswer(item)"
            >
              {{ isAnswerExpanded(item) ? "Show less" : "Show more" }}
            </button>
            <p class="audit-meta">
              <span>{{ item.sources?.length || 0 }} sources</span>
              <span v-if="item.conversation_id">conversation {{ item.conversation_id }}</span>
              <span v-if="item.sources?.[0]">{{ formatSourceName(item.sources[0].document_id) }}</span>
            </p>
          </article>
        </div>
        <div v-if="missingDocFeedback.length > pageSize" class="pagination">
          <button
            class="secondary-button"
            type="button"
            :disabled="missingDocPage <= 1"
            @click="setMissingDocPage(missingDocPage - 1)"
          >
            Previous
          </button>
          <span>Page {{ missingDocPage }} of {{ missingDocTotalPages }}</span>
          <button
            class="secondary-button"
            type="button"
            :disabled="missingDocPage >= missingDocTotalPages"
            @click="setMissingDocPage(missingDocPage + 1)"
          >
            Next
          </button>
        </div>
        <p v-if="missingDocFeedback.length === 0 && !feedbackLoading" class="empty-state">
          No missing doc requests yet.
        </p>
      </template>
    </section>
  </div>
</template>
