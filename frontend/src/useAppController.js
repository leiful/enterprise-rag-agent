import { computed, onBeforeUnmount, onMounted } from "vue";
import { useAdminData } from "./useAdminData";
import { useChatConversations } from "./useChatConversations";
import { useFeedback } from "./useFeedback";
import { useKnowledgeManagement } from "./useKnowledgeManagement";
import { useAdminUsers } from "./useAdminUsers";
import { createAppWorkspaceBindings } from "./appWorkspaceBindings";
import { useAppState } from "./useAppState";
import { API_BASE, DAILY_TOKEN_WARNING_THRESHOLD } from "./appConfig";
import { decodeSourcesHeader, formatNumber, normalizeMessages } from "./formatters";
import { paginateItems, totalPages } from "./pagination";
import { useModelUsage } from "./useModelUsage";
import { cloneMessages, responseError } from "./uiHelpers";
import { useAuthSession } from "./useAuthSession";


export function useAppController() {
const state = useAppState();
const {
  input, username, password, currentUser, currentUserRole, conversations, currentConversationId,
  activeView, loading, conversationLoading, authLoading, knowledgeLoading, error, knowledgeError,
  knowledgeFileInput, chatView, settingsMenu, selectedKnowledgeFile, knowledgeNotes,
  knowledgeDepartment, knowledgeDocuments, knowledgeSources, knowledgeSearchQuery,
  knowledgeSearchResults, knowledgeSearchLoading, knowledgeSearchError, knowledgeIndexJob,
  ragStatus, ragStatusLoading, ragStatusError, failedIndexJobsExpanded, acknowledgingFailedJobs,
  users, usersLoading, usersError, departments, departmentsLoading, departmentsError,
  newDepartmentName, newUserUsername, newUserPassword, newUserRole, newUserDepartment,
  userEdits, knowledgeAudits, auditLoading, auditError, ragEval, ragEvalLoading, ragEvalError,
  ragEvalSuites, selectedRagEvalSuite, ragEvalRunning, modelUsage, modelUsageLoading,
  modelUsageError, ragFeedback, ragFeedbackSummary, feedbackLoading, feedbackError,
  operationsView, operationsTab, usersTab, knowledgeTab, feedbackPage, auditPage, missingDocPage,
  usageEventsPage, deepseekBalance, balanceLoading, balanceError, messages, isAuthenticated,
  isAdmin, missingDocFeedback, pageSize, feedbackTotalPages, auditTotalPages,
  missingDocTotalPages, chatAdmissionLabel,
} = state;
const dailyTokenWarningThreshold = DAILY_TOKEN_WARNING_THRESHOLD;
const {
  modelUsagePeriod,
  usageTrendTab,
  usageTrendTooltip,
  modelUsageRows,
  modelUsageTotals,
  modelUsageScopeRows,
  modelUsageTotalTokens,
  todayTokenTotal,
  shouldShowDailyTokenWarning,
  usageTrendCurrentHourIndex,
  modelUsageTrendRows,
  modelUsageTrendAxisTicks,
  modelUsageTrendAxisTickStyle,
  modelUsageTrendSeries,
  modelUsageTrendBarSegments,
  showUsageTrendTooltip,
  hideUsageTrendTooltip,
  modelUsageRecentEvents,
  formatUsageTrendBucket,
  formatUsageTrendAxisBucket,
  setModelUsagePeriod: setModelUsagePeriodValue,
} = useModelUsage({
  modelUsage,
  ragStatus,
  isAdmin,
  dailyTokenWarningThreshold,
});
const usageEventsTotalPages = computed(() => totalPages(modelUsageRecentEvents(modelUsagePeriod.value).length, pageSize));
const pagedModelUsageEvents = computed(() => paginateItems(modelUsageRecentEvents(modelUsagePeriod.value), usageEventsPage.value, pageSize));
const {
  loadKnowledgeDocuments,
  loadKnowledgeSources,
  loadRagStatus,
  acknowledgeFailedIndexJobs,
  loadUsers,
  loadDepartments,
  loadKnowledgeAudits,
  loadRagEval,
  loadRagEvalSuites,
  loadModelUsage,
  runRagEval,
  loadRagFeedback,
  loadDeepseekBalance,
  formatDeepseekBalance,
  ragStatusClass,
} = useAdminData({
  API_BASE,
  refs: {
    isAdmin,
    knowledgeDocuments,
    knowledgeSources,
    ragStatus,
    ragStatusLoading,
    ragStatusError,
    acknowledgingFailedJobs,
    users,
    usersLoading,
    usersError,
    departments,
    departmentsLoading,
    departmentsError,
    userEdits,
    knowledgeAudits,
    auditLoading,
    auditError,
    auditPage,
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
    feedbackPage,
    missingDocPage,
    deepseekBalance,
    balanceLoading,
    balanceError,
  },
  pageSize,
  missingDocFeedback,
});

function adminDashboardLoaders() {
  return [
    ["knowledge sources", loadKnowledgeSources],
    ["knowledge documents", loadKnowledgeDocuments],
    ["rag status", loadRagStatus],
    ["departments", loadDepartments],
    ["users", loadUsers],
    ["knowledge audits", loadKnowledgeAudits],
    ["rag eval suites", loadRagEvalSuites],
    ["rag eval", loadRagEval],
    ["model usage", loadModelUsage],
    ["rag feedback", loadRagFeedback],
    ["deepseek balance", loadDeepseekBalance],
  ];
}

let conversationMessagesCache = null;
let cacheCurrentConversation;
let restoreConversation;
let openNewChat;
let openConversation;
let sendMessageStream;
const authSession = useAuthSession({
  API_BASE,
  refs: state,
  loaders: {
    adminDashboardLoaders,
    loadRagStatus,
    loadConversations: (...args) => loadConversations(...args),
    restoreConversation: (...args) => restoreConversation(...args),
  },
  helpers: {
    get conversationMessagesCache() {
      return conversationMessagesCache;
    },
  },
});

const { checkSession, closeSettingsMenu, loadConversations, login, logout, onDocumentPointerDown, stopRagStatusRefresh } = authSession;
({
  conversationMessagesCache,
  cacheCurrentConversation,
  restoreConversation,
  openNewChat,
  openConversation,
  sendMessageStream,
} = useChatConversations({
  API_BASE,
  refs: {
    input,
    activeView,
    loading,
    conversationLoading,
    error,
    chatView,
    conversations,
    currentConversationId,
    messages,
    deepseekBalance,
    balanceError,
    balanceLoading,
  },
  loaders: {
    loadConversations,
    loadDeepseekBalance,
  },
  helpers: {
    cloneMessages,
      normalizeMessages,
    decodeSourcesHeader,
  },
}));

const {
  defaultKnowledgeTopK,
  defaultKnowledgeMinScore,
  chooseKnowledgeFile,
  onKnowledgeFileChange,
  uploadKnowledgeFile,
  pollKnowledgeIndexJob,
  pollKnowledgeIndexJobs,
  deleteKnowledgeDocument,
  reindexAllKnowledgeDocuments,
  syncEnabledKnowledgeSources,
  clearMissingKnowledgeFiles,
  deduplicateKnowledgeDocuments,
  searchKnowledge,
} = useKnowledgeManagement({
  API_BASE,
  responseError,
  refs: {
    ragStatus,
    knowledgeFileInput,
    selectedKnowledgeFile,
    knowledgeNotes,
    knowledgeDepartment,
    knowledgeLoading,
    knowledgeError,
    knowledgeIndexJob,
    knowledgeSources,
    knowledgeSearchQuery,
    knowledgeSearchResults,
    knowledgeSearchLoading,
    knowledgeSearchError,
  },
  loaders: {
    loadKnowledgeSources,
    loadKnowledgeDocuments,
    loadRagStatus,
    loadKnowledgeAudits,
  },
});

const {
  createUserAccount,
  userEditChanged,
  saveUserAccount,
  createDepartmentItem,
  deleteDepartmentItem,
} = useAdminUsers({
  API_BASE,
  responseError,
  refs: {
    isAdmin,
    usersLoading,
    usersError,
    newUserUsername,
    newUserPassword,
    newUserRole,
    newUserDepartment,
    userEdits,
    departmentsLoading,
    departmentsError,
    departments,
    newDepartmentName,
    knowledgeDepartment,
  },
  loaders: {
    loadUsers,
    loadDepartments,
  },
});

const { submitFeedback } = useFeedback({
  API_BASE,
  responseError,
  refs: {
    messages,
    currentConversationId,
    isAdmin,
  },
  loaders: {
    cacheCurrentConversation,
    loadRagFeedback,
    loadRagStatus,
  },
});

const modelUsageBindings = {
  modelUsagePeriod,
  usageTrendTab,
  usageTrendTooltip,
  modelUsageTrendRows,
  modelUsageTrendBarSegments,
  showUsageTrendTooltip,
  hideUsageTrendTooltip,
  modelUsageTrendAxisTicks,
  modelUsageTrendAxisTickStyle,
  modelUsageTrendSeries,
  modelUsageRecentEvents,
  modelUsageTotalTokens,
  formatUsageTrendBucket,
  formatUsageTrendAxisBucket,
};

const adminDataBindings = {
  acknowledgeFailedIndexJobs,
  loadKnowledgeAudits,
  loadRagEval,
  loadRagFeedback,
  ragStatusClass,
  runRagEval,
};

const knowledgeBindings = {
  clearMissingKnowledgeFiles,
  deduplicateKnowledgeDocuments,
  defaultKnowledgeMinScore,
  deleteKnowledgeDocument,
  onKnowledgeFileChange,
  reindexAllKnowledgeDocuments,
  searchKnowledge,
  syncEnabledKnowledgeSources,
  uploadKnowledgeFile,
};

const userBindings = {
  createDepartmentItem,
  createUserAccount,
  deleteDepartmentItem,
  saveUserAccount,
  userEditChanged,
};
function setOperationsTab(tab) {
  operationsTab.value = tab;
}

function setUsersTab(tab) {
  usersTab.value = tab;
}

function setKnowledgeTab(tab) {
  knowledgeTab.value = tab;
  if (tab === "evaluation") {
    loadRagEvalSuites();
    loadRagEval();
  }
}

function setFeedbackPage(page) {
  feedbackPage.value = Math.max(1, Math.min(page, feedbackTotalPages.value));
}

function setAuditPage(page) {
  auditPage.value = Math.max(1, Math.min(page, auditTotalPages.value));
}

function setMissingDocPage(page) {
  missingDocPage.value = Math.max(1, Math.min(page, missingDocTotalPages.value));
}

function setUsageEventsPage(page) {
  usageEventsPage.value = Math.max(1, Math.min(page, usageEventsTotalPages.value));
}

function setModelUsagePeriod(period) {
  modelUsagePeriod.value = period;
  usageEventsPage.value = 1;
}

function setUsageTrendTab(tab) {
  usageTrendTab.value = tab;
}

function openOperationsOverview() {
  operationsView.value = "overview";
}

function openTokenMonitor() {
  activeView.value = "token-monitor";
  closeSettingsMenu();
  loadModelUsage();
}

function openMissingDocManagement() {
  activeView.value = "operations";
  operationsView.value = "missing-docs";
  missingDocPage.value = 1;
}

const workspaceBindings = createAppWorkspaceBindings({
  state: { ...state, usageEventsTotalPages, pagedModelUsageEvents },
  modelUsage: modelUsageBindings,
  adminData: adminDataBindings,
  chat: { openNewChat, openConversation, sendMessageStream },
  knowledge: knowledgeBindings,
  users: userBindings,
  feedback: { submitFeedback },
  navigation: {
    openMissingDocManagement,
    openOperationsOverview,
    setAuditPage,
    setFeedbackPage,
    setKnowledgeTab,
    setMissingDocPage,
    setModelUsagePeriod,
    setOperationsTab,
    setUsageEventsPage,
    setUsersTab,
    setUsageTrendTab,
  },
});
onMounted(() => {
  document.addEventListener("pointerdown", onDocumentPointerDown);
});

onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", onDocumentPointerDown);
  stopRagStatusRefresh();
});


  checkSession();

  return {
    username,
    password,
    authLoading,
    isAuthenticated,
    isAdmin,
    currentUser,
    activeView,
    chatAdmissionLabel,
    shouldShowDailyTokenWarning,
    formatNumber,
    todayTokenTotal,
    balanceError,
    deepseekBalance,
    formatDeepseekBalance,
    settingsMenu,
    closeSettingsMenu,
    openTokenMonitor,
    openOperationsOverview,
    logout,
    login,
    error,
    workspaceBindings,
  };
}
