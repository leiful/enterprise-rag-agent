import { computed, ref } from "vue";
import { DEFAULT_RAG_EVAL_SUITES, PAGE_SIZE } from "./appConfig.js";
import { filterFeedbackByType } from "./feedbackFilters.js";
import { paginateItems, totalPages } from "./pagination.js";
import { emptyMessages } from "./uiHelpers.js";

export function useAppState() {
  const input = ref("");
  const username = ref("");
  const password = ref("");
  const currentUser = ref("");
  const currentUserRole = ref("");
  const conversations = ref([]);
  const currentConversationId = ref(null);
  const activeView = ref("chat");
  const loading = ref(false);
  const conversationLoading = ref(false);
  const authLoading = ref(false);
  const knowledgeLoading = ref(false);
  const error = ref("");
  const knowledgeError = ref("");
  const knowledgeFileInput = ref(null);
  const chatView = ref(null);
  const settingsMenu = ref(null);
  const selectedKnowledgeFile = ref(null);
  const knowledgeNotes = ref("");
  const knowledgeDepartment = ref("");
  const knowledgeDocuments = ref([]);
  const knowledgeSources = ref([]);
  const knowledgeSearchQuery = ref("");
  const knowledgeSearchResults = ref([]);
  const knowledgeSearchLoading = ref(false);
  const knowledgeSearchError = ref("");
  const knowledgeIndexJob = ref(null);
  const ragStatus = ref(null);
  const ragStatusLoading = ref(false);
  const ragStatusError = ref("");
  const failedIndexJobsExpanded = ref(false);
  const acknowledgingFailedJobs = ref(false);
  const users = ref([]);
  const usersLoading = ref(false);
  const usersError = ref("");
  const departments = ref([]);
  const departmentsLoading = ref(false);
  const departmentsError = ref("");
  const newDepartmentName = ref("");
  const newUserUsername = ref("");
  const newUserPassword = ref("");
  const newUserRole = ref("user");
  const newUserDepartment = ref("");
  const userEdits = ref({});
  const knowledgeAudits = ref([]);
  const auditLoading = ref(false);
  const auditError = ref("");
  const ragEval = ref(null);
  const ragEvalLoading = ref(false);
  const ragEvalError = ref("");
  const ragEvalSuites = ref([...DEFAULT_RAG_EVAL_SUITES]);
  const selectedRagEvalSuite = ref("uploaded_pdfs");
  const ragEvalRunning = ref(false);
  const modelUsage = ref(null);
  const modelUsageLoading = ref(false);
  const modelUsageError = ref("");
  const ragFeedback = ref([]);
  const ragFeedbackSummary = ref(null);
  const feedbackLoading = ref(false);
  const feedbackError = ref("");
  const selectedFeedbackType = ref("");
  const operationsView = ref("overview");
  const operationsTab = ref("feedback");
  const usersTab = ref("users");
  const knowledgeTab = ref("documents");
  const feedbackPage = ref(1);
  const auditPage = ref(1);
  const missingDocPage = ref(1);
  const usageEventsPage = ref(1);
  const deepseekBalance = ref(null);
  const balanceLoading = ref(false);
  const balanceError = ref("");
  const messages = ref([...emptyMessages()]);

  const isAuthenticated = ref(false);
  const isAdmin = computed(() => currentUserRole.value === "admin");
  const hasEnabledKnowledgeSources = computed(() => knowledgeSources.value.some((source) => source.enabled));
  const missingDocFeedback = computed(() =>
    ragFeedback.value.filter((item) => item.feedback_type === "missing_doc"),
  );
  const filteredRagFeedback = computed(() =>
    filterFeedbackByType(ragFeedback.value, selectedFeedbackType.value),
  );
  const pageSize = PAGE_SIZE;
  const pagedRagFeedback = computed(() => paginateItems(filteredRagFeedback.value, feedbackPage.value, pageSize));
  const pagedKnowledgeAudits = computed(() => paginateItems(knowledgeAudits.value, auditPage.value, pageSize));
  const pagedMissingDocFeedback = computed(() => paginateItems(missingDocFeedback.value, missingDocPage.value, pageSize));
  const feedbackTotalPages = computed(() => totalPages(filteredRagFeedback.value.length, pageSize));
  const auditTotalPages = computed(() => totalPages(knowledgeAudits.value.length, pageSize));
  const missingDocTotalPages = computed(() => totalPages(missingDocFeedback.value.length, pageSize));
  const chatAdmissionLabel = computed(() => {
    const active = ragStatus.value?.active_users;
    if (active === undefined || active === null) {
      return "在线: 0";
    }
    return `在线: ${active}`;
  });
  const selectedRagEvalSuiteInfo = computed(() =>
    ragEvalSuites.value.find((suite) => suite.id === selectedRagEvalSuite.value),
  );

  return {
    input,
    username,
    password,
    currentUser,
    currentUserRole,
    conversations,
    currentConversationId,
    activeView,
    loading,
    conversationLoading,
    authLoading,
    knowledgeLoading,
    error,
    knowledgeError,
    knowledgeFileInput,
    chatView,
    settingsMenu,
    selectedKnowledgeFile,
    knowledgeNotes,
    knowledgeDepartment,
    knowledgeDocuments,
    knowledgeSources,
    knowledgeSearchQuery,
    knowledgeSearchResults,
    knowledgeSearchLoading,
    knowledgeSearchError,
    knowledgeIndexJob,
    ragStatus,
    ragStatusLoading,
    ragStatusError,
    failedIndexJobsExpanded,
    acknowledgingFailedJobs,
    users,
    usersLoading,
    usersError,
    departments,
    departmentsLoading,
    departmentsError,
    newDepartmentName,
    newUserUsername,
    newUserPassword,
    newUserRole,
    newUserDepartment,
    userEdits,
    knowledgeAudits,
    auditLoading,
    auditError,
    ragEval,
    ragEvalLoading,
    ragEvalError,
    ragEvalSuites,
    selectedRagEvalSuite,
    ragEvalRunning,
    modelUsage,
    modelUsageLoading,
    modelUsageError,
    ragFeedback,
    ragFeedbackSummary,
    feedbackLoading,
    feedbackError,
    selectedFeedbackType,
    operationsView,
    operationsTab,
    usersTab,
    knowledgeTab,
    feedbackPage,
    auditPage,
    missingDocPage,
    usageEventsPage,
    deepseekBalance,
    balanceLoading,
    balanceError,
    messages,
    isAuthenticated,
    isAdmin,
    hasEnabledKnowledgeSources,
    filteredRagFeedback,
    missingDocFeedback,
    pageSize,
    pagedRagFeedback,
    pagedKnowledgeAudits,
    pagedMissingDocFeedback,
    feedbackTotalPages,
    auditTotalPages,
    missingDocTotalPages,
    chatAdmissionLabel,
    selectedRagEvalSuiteInfo,
  };
}
