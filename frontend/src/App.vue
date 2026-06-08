<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
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
const messagesContainer = ref(null);
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
const defaultRagEvalSuites = [
  { id: "core", name: "Core Regression", question_count: 20 },
  { id: "acceptance", name: "Acceptance", question_count: 12 },
  { id: "ragbench", name: "RAGBench Sample", question_count: 5 },
];
const ragEvalSuites = ref([...defaultRagEvalSuites]);
const selectedRagEvalSuite = ref("core");
const ragEvalRunning = ref(false);
const ragFeedback = ref([]);
const ragFeedbackSummary = ref(null);
const feedbackLoading = ref(false);
const feedbackError = ref("");
const operationsView = ref("overview");
const operationsTab = ref("feedback");
const usersTab = ref("users");
const knowledgeTab = ref("documents");
const feedbackPage = ref(1);
const auditPage = ref(1);
const missingDocPage = ref(1);
const deepseekBalance = ref(null);
const balanceLoading = ref(false);
const balanceError = ref("");
const emptyMessage = {
  role: "assistant",
  content: "Ready. Ask me to inspect project files, explain code, or run safe checks.",
};
const messages = ref([
  emptyMessage,
]);
const conversationMessagesCache = new Map();
let conversationLoadToken = 0;
let ragStatusRefreshTimer = null;

const isAuthenticated = ref(false);
const isAdmin = computed(() => currentUserRole.value === "admin");
const hasEnabledKnowledgeSources = computed(() => knowledgeSources.value.some((source) => source.enabled));
const missingDocFeedback = computed(() =>
  ragFeedback.value.filter((item) => item.feedback_type === "missing_doc"),
);
const pageSize = 8;
const pagedRagFeedback = computed(() => paginateItems(ragFeedback.value, feedbackPage.value));
const pagedKnowledgeAudits = computed(() => paginateItems(knowledgeAudits.value, auditPage.value));
const pagedMissingDocFeedback = computed(() => paginateItems(missingDocFeedback.value, missingDocPage.value));
const feedbackTotalPages = computed(() => totalPages(ragFeedback.value.length));
const auditTotalPages = computed(() => totalPages(knowledgeAudits.value.length));
const missingDocTotalPages = computed(() => totalPages(missingDocFeedback.value.length));
const chatAdmissionLabel = computed(() => {
  const admission = ragStatus.value?.chat_admission;
  if (!admission) {
    return "0/20";
  }
  return `${admission.active || 0}/${admission.max_concurrent || 20}`;
});

function resolveUserRole(data) {
  if (data.role) {
    return data.role;
  }
  return data.username === "admin" ? "admin" : "";
}

function closeSettingsMenu() {
  if (settingsMenu.value) {
    settingsMenu.value.open = false;
  }
}

function onDocumentPointerDown(event) {
  if (!settingsMenu.value?.open) {
    return;
  }
  if (!settingsMenu.value.contains(event.target)) {
    closeSettingsMenu();
  }
}

function stopRagStatusRefresh() {
  if (ragStatusRefreshTimer) {
    clearInterval(ragStatusRefreshTimer);
    ragStatusRefreshTimer = null;
  }
}

function startRagStatusRefresh() {
  stopRagStatusRefresh();
  if (!isAdmin.value) {
    return;
  }
  ragStatusRefreshTimer = window.setInterval(() => {
    if (isAuthenticated.value && isAdmin.value) {
      loadRagStatus({ silent: true });
    }
  }, 5000);
}

async function responseError(response, fallback) {
  try {
    const data = await response.json();
    return data.detail || fallback;
  } catch {
    return fallback;
  }
}

async function checkSession() {
  authLoading.value = true;
  error.value = "";

  try {
    const response = await fetch(`${API_BASE}/me`, {
      credentials: "include",
    });
    const data = await response.json();
    isAuthenticated.value = Boolean(data.authenticated);
    currentUser.value = data.username || "";
    currentUserRole.value = resolveUserRole(data);
    if (isAuthenticated.value) {
      await loadConversations();
      if (isAdmin.value) {
        await loadKnowledgeSources();
        await loadKnowledgeDocuments();
        await loadRagStatus();
        await loadDepartments();
        await loadUsers();
        await loadKnowledgeAudits();
        await loadRagEvalSuites();
        await loadRagEval();
        await loadRagFeedback();
        await loadDeepseekBalance();
        startRagStatusRefresh();
      } else {
        activeView.value = "chat";
        stopRagStatusRefresh();
      }
      await restoreConversation();
    }
  } catch (err) {
    error.value = err.message || "Session check failed";
  } finally {
    authLoading.value = false;
  }
}

async function login() {
  if (!username.value.trim() || !password.value || authLoading.value) {
    return;
  }

  authLoading.value = true;
  error.value = "";

  try {
    const response = await fetch(`${API_BASE}/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include",
      body: JSON.stringify({
        username: username.value.trim(),
        password: password.value,
      }),
    });

    if (!response.ok) {
      throw new Error(`Login failed with status ${response.status}`);
    }

    const data = await response.json();
    isAuthenticated.value = Boolean(data.authenticated);
    currentUser.value = data.username || username.value.trim();
    currentUserRole.value = resolveUserRole(data);
    password.value = "";
    await loadConversations();
    if (isAdmin.value) {
      await loadKnowledgeSources();
      await loadKnowledgeDocuments();
      await loadRagStatus();
      await loadDepartments();
      await loadUsers();
      await loadKnowledgeAudits();
      await loadRagEvalSuites();
      await loadRagEval();
      await loadRagFeedback();
      await loadDeepseekBalance();
      startRagStatusRefresh();
    } else {
      activeView.value = "chat";
      stopRagStatusRefresh();
    }
    await restoreConversation();
  } catch (err) {
    error.value = err.message || "Login failed";
  } finally {
    authLoading.value = false;
  }
}

async function logout() {
  authLoading.value = true;
  error.value = "";

  try {
    await fetch(`${API_BASE}/logout`, {
      method: "POST",
      credentials: "include",
    });
  } finally {
    stopRagStatusRefresh();
    isAuthenticated.value = false;
    currentUser.value = "";
    currentUserRole.value = "";
    currentConversationId.value = null;
    conversations.value = [];
    knowledgeDocuments.value = [];
    knowledgeSources.value = [];
    ragStatus.value = null;
    ragStatusError.value = "";
    departments.value = [];
    departmentsError.value = "";
    newDepartmentName.value = "";
    users.value = [];
    usersError.value = "";
    knowledgeAudits.value = [];
    auditError.value = "";
    ragEval.value = null;
    ragEvalError.value = "";
    ragFeedback.value = [];
    ragFeedbackSummary.value = null;
    feedbackError.value = "";
    deepseekBalance.value = null;
    balanceError.value = "";
    messages.value = [emptyMessage];
    conversationMessagesCache.clear();
    localStorage.removeItem("currentConversationId");
    password.value = "";
    authLoading.value = false;
  }
}

async function loadConversations() {
  const response = await fetch(`${API_BASE}/conversations`, {
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(`Failed to load conversations with status ${response.status}`);
  }

  const data = await response.json();
  conversations.value = data.conversations || [];
}

async function loadKnowledgeDocuments() {
  const response = await fetch(`${API_BASE}/knowledge/documents`, {
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(`Failed to load knowledge documents with status ${response.status}`);
  }

  const data = await response.json();
  knowledgeDocuments.value = data.documents || [];
}

async function loadKnowledgeSources() {
  const response = await fetch(`${API_BASE}/knowledge/sources`, {
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(`Failed to load knowledge sources with status ${response.status}`);
  }

  const data = await response.json();
  knowledgeSources.value = data.sources || [];
}

async function loadRagStatus(options = {}) {
  if (!isAdmin.value) {
    ragStatus.value = null;
    return;
  }

  const silent = Boolean(options.silent);
  if (!silent) {
    ragStatusLoading.value = true;
    ragStatusError.value = "";
  }

  try {
    const response = await fetch(`${API_BASE}/admin/rag/status`, {
      credentials: "include",
    });

    if (!response.ok) {
      throw new Error(await responseError(response, `Failed to load RAG status with status ${response.status}`));
    }

    ragStatus.value = await response.json();
  } catch (err) {
    if (!silent) {
      ragStatusError.value = err.message || "Failed to load RAG status";
    }
  } finally {
    if (!silent) {
      ragStatusLoading.value = false;
    }
  }
}

async function loadUsers() {
  if (!isAdmin.value) {
    users.value = [];
    return;
  }

  usersLoading.value = true;
  usersError.value = "";

  try {
    const response = await fetch(`${API_BASE}/admin/users`, {
      credentials: "include",
    });

    if (!response.ok) {
      throw new Error(await responseError(response, `Failed to load users with status ${response.status}`));
    }

    const data = await response.json();
    users.value = data.users || [];
    userEdits.value = Object.fromEntries(
      users.value.map((user) => [
        user.id,
        {
          role: user.role,
          department: user.role === "admin" ? "" : user.departments?.[0] || "",
        },
      ]),
    );
  } catch (err) {
    usersError.value = err.message || "Failed to load users";
  } finally {
    usersLoading.value = false;
  }
}

async function loadDepartments() {
  if (!isAdmin.value) {
    departments.value = [];
    return;
  }

  departmentsLoading.value = true;
  departmentsError.value = "";

  try {
    const response = await fetch(`${API_BASE}/admin/departments`, {
      credentials: "include",
    });

    if (!response.ok) {
      throw new Error(await responseError(response, `Failed to load departments with status ${response.status}`));
    }

    const data = await response.json();
    departments.value = data.departments || [];
  } catch (err) {
    departmentsError.value = err.message || "Failed to load departments";
  } finally {
    departmentsLoading.value = false;
  }
}

async function loadKnowledgeAudits() {
  if (!isAdmin.value) {
    knowledgeAudits.value = [];
    return;
  }

  auditLoading.value = true;
  auditError.value = "";

  try {
    const response = await fetch(`${API_BASE}/admin/knowledge-audit?limit=50`, {
      credentials: "include",
    });

    if (!response.ok) {
      throw new Error(await responseError(response, `Failed to load audit with status ${response.status}`));
    }

    const data = await response.json();
    knowledgeAudits.value = data.audits || [];
    auditPage.value = Math.min(auditPage.value, totalPages(knowledgeAudits.value.length));
  } catch (err) {
    auditError.value = err.message || "Failed to load audit";
  } finally {
    auditLoading.value = false;
  }
}

async function loadRagEval() {
  if (!isAdmin.value) {
    ragEval.value = null;
    return;
  }

  if (ragEvalSuites.value.length === 0) {
    ragEvalSuites.value = [...defaultRagEvalSuites];
  }
  ragEvalLoading.value = true;
  ragEvalError.value = "";

  try {
    const response = await fetch(`${API_BASE}/admin/rag/eval`, {
      credentials: "include",
    });

    if (!response.ok) {
      throw new Error(await responseError(response, `Failed to load RAG evaluation with status ${response.status}`));
    }

    ragEval.value = await response.json();
  } catch (err) {
    ragEvalError.value = err.message || "Failed to load RAG evaluation";
  } finally {
    ragEvalLoading.value = false;
  }
}

async function loadRagEvalSuites() {
  if (!isAdmin.value) {
    ragEvalSuites.value = [];
    return;
  }

  try {
    const response = await fetch(`${API_BASE}/admin/rag/eval/suites`, {
      credentials: "include",
    });

    if (!response.ok) {
      throw new Error(await responseError(response, `Failed to load RAG evaluation suites with status ${response.status}`));
    }

    const data = await response.json();
    ragEvalSuites.value = data.suites || [];
    if (!ragEvalSuites.value.some((suite) => suite.id === selectedRagEvalSuite.value)) {
      selectedRagEvalSuite.value = ragEvalSuites.value[0]?.id || "core";
    }
  } catch (err) {
    ragEvalSuites.value = [...defaultRagEvalSuites];
  }
}

async function runRagEval() {
  if (!isAdmin.value || ragEvalRunning.value) {
    return;
  }

  ragEvalRunning.value = true;
  ragEvalError.value = "";

  try {
    const response = await fetch(`${API_BASE}/admin/rag/eval/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        suite: selectedRagEvalSuite.value,
        skip_chat: false,
        skip_upload: false,
      }),
    });

    if (!response.ok) {
      throw new Error(await responseError(response, `RAG evaluation failed with status ${response.status}`));
    }

    await response.json();
    await loadRagEval();
  } catch (err) {
    ragEvalError.value = err.message || "Failed to run RAG evaluation";
  } finally {
    ragEvalRunning.value = false;
  }
}

async function loadRagFeedback() {
  if (!isAdmin.value) {
    ragFeedback.value = [];
    ragFeedbackSummary.value = null;
    return;
  }

  feedbackLoading.value = true;
  feedbackError.value = "";

  try {
    const response = await fetch(`${API_BASE}/admin/feedback?limit=50`, {
      credentials: "include",
    });

    if (!response.ok) {
      throw new Error(await responseError(response, `Failed to load feedback with status ${response.status}`));
    }

    const data = await response.json();
    ragFeedbackSummary.value = data.summary || null;
    ragFeedback.value = data.feedback || [];
    feedbackPage.value = Math.min(feedbackPage.value, totalPages(ragFeedback.value.length));
    missingDocPage.value = Math.min(missingDocPage.value, totalPages(missingDocFeedback.value.length));
  } catch (err) {
    feedbackError.value = err.message || "Failed to load feedback";
  } finally {
    feedbackLoading.value = false;
  }
}

async function loadDeepseekBalance() {
  if (balanceLoading.value) {
    return;
  }

  balanceLoading.value = true;
  balanceError.value = "";

  try {
    const response = await fetch(`${API_BASE}/billing/deepseek-balance`, {
      credentials: "include",
    });

    if (!response.ok) {
      throw new Error(`Balance request failed with status ${response.status}`);
    }

    deepseekBalance.value = await response.json();
  } catch (err) {
    balanceError.value = err.message || "Balance unavailable";
    deepseekBalance.value = null;
  } finally {
    balanceLoading.value = false;
  }
}

function formatDeepseekBalance() {
  const balances = deepseekBalance.value?.balance_infos || [];
  if (balances.length === 0) {
    return balanceLoading.value ? "Balance..." : "Balance unavailable";
  }

  return balances
    .map((balance) => `${balance.currency === "CNY" ? "DS" : balance.currency} ${balance.total_balance}`)
    .join(" / ");
}

function ragStatusClass() {
  const status = ragStatus.value?.status || "unknown";
  return {
    ok: status === "ok",
    degraded: status === "degraded",
    error: status === "error",
  };
}

function formatStatusCount(counts, key) {
  return Number(counts?.[key] || 0);
}

function formatRagFeature(value) {
  return value ? "on" : "off";
}

function formatPercent(value) {
  return `${(Number(value || 0) * 100).toFixed(0)}%`;
}

function feedbackTypeLabel(type) {
  const labels = {
    useful: "Useful",
    not_useful: "Not useful",
    wrong_source: "Wrong source",
    outdated: "Outdated",
    missing_doc: "Missing doc",
  };
  return labels[type] || type;
}

function feedbackOptions(message) {
  if (message.feedbackSent) {
    return [];
  }
  return message.sources?.length
    ? ["useful", "not_useful", "wrong_source", "outdated", "missing_doc"]
    : ["useful", "not_useful", "missing_doc"];
}

function totalPages(total) {
  return Math.max(1, Math.ceil(Number(total || 0) / pageSize));
}

function paginateItems(items, page) {
  const start = (Math.max(1, page) - 1) * pageSize;
  return items.slice(start, start + pageSize);
}

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

function openOperationsOverview() {
  operationsView.value = "overview";
}

function openMissingDocManagement() {
  activeView.value = "operations";
  operationsView.value = "missing-docs";
  missingDocPage.value = 1;
}

function defaultKnowledgeTopK() {
  return Number(ragStatus.value?.retrieval?.default_top_k || 5);
}

function defaultKnowledgeMinScore() {
  return Number(ragStatus.value?.retrieval?.default_min_score ?? 0.25);
}

function chooseKnowledgeFile() {
  knowledgeFileInput.value?.click();
}

function onKnowledgeFileChange(event) {
  selectedKnowledgeFile.value = event.target.files?.[0] || null;
}

async function uploadKnowledgeFile() {
  const file = selectedKnowledgeFile.value;

  if (!file || knowledgeLoading.value) {
    return;
  }

  if (file.size > 50 * 1024 * 1024) {
    knowledgeError.value = "File is larger than 50MB.";
    return;
  }

  knowledgeLoading.value = true;
  knowledgeError.value = "";
  knowledgeIndexJob.value = null;

  try {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("notes", knowledgeNotes.value.trim());
    formData.append(
      "metadata",
      JSON.stringify({
        department: knowledgeDepartment.value.trim(),
      }),
    );

    const response = await fetch(`${API_BASE}/knowledge/upload`, {
      method: "POST",
      credentials: "include",
      body: formData,
    });

    if (!response.ok) {
      throw new Error(
        await responseError(response, `Upload failed with status ${response.status}`),
      );
    }

    const data = await response.json();
    knowledgeIndexJob.value = data;
    selectedKnowledgeFile.value = null;
    knowledgeNotes.value = "";
    knowledgeDepartment.value = "";
    if (knowledgeFileInput.value) {
      knowledgeFileInput.value.value = "";
    }
    await pollKnowledgeIndexJob(data.job_id);
  } catch (err) {
    knowledgeError.value = err.message || "Upload failed";
  } finally {
    knowledgeLoading.value = false;
  }
}

async function createUserAccount() {
  if (!isAdmin.value || usersLoading.value) {
    return;
  }

  const username = newUserUsername.value.trim();
  const password = newUserPassword.value;
  const role = newUserRole.value;
  const selectedDepartments = role === "admin" || !newUserDepartment.value ? [] : [newUserDepartment.value];

  if (!username || !password) {
    usersError.value = "Username and password are required.";
    return;
  }
  if (role === "user" && !newUserDepartment.value) {
    usersError.value = "Department is required for user accounts.";
    return;
  }

  usersLoading.value = true;
  usersError.value = "";

  try {
    const response = await fetch(`${API_BASE}/admin/users`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include",
      body: JSON.stringify({ username, password, role, departments: selectedDepartments }),
    });

    if (!response.ok) {
      throw new Error(await responseError(response, `Create user failed with status ${response.status}`));
    }

    newUserUsername.value = "";
    newUserPassword.value = "";
    newUserRole.value = "user";
    newUserDepartment.value = "";
    await loadUsers();
  } catch (err) {
    usersError.value = err.message || "Create user failed";
  } finally {
    usersLoading.value = false;
  }
}

function userEditChanged(user) {
  const edit = userEdits.value[user.id] || {};
  const department = edit.role === "admin" ? "" : edit.department || "";
  const currentDepartment = user.role === "admin" ? "" : user.departments?.[0] || "";
  return edit.role !== user.role || department !== currentDepartment;
}

async function saveUserAccount(user) {
  if (!isAdmin.value || usersLoading.value) {
    return;
  }
  const edit = userEdits.value[user.id] || {};
  const role = edit.role || user.role;
  const departments = role === "admin" || !edit.department ? [] : [edit.department];
  if (role === "user" && !edit.department) {
    usersError.value = "Department is required for user accounts.";
    return;
  }

  usersLoading.value = true;
  usersError.value = "";
  try {
    const response = await fetch(`${API_BASE}/admin/users/${encodeURIComponent(user.id)}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include",
      body: JSON.stringify({ role, departments }),
    });
    if (!response.ok) {
      throw new Error(await responseError(response, `Update user failed with status ${response.status}`));
    }
    await loadUsers();
  } catch (err) {
    usersError.value = err.message || "Update user failed";
  } finally {
    usersLoading.value = false;
  }
}

async function createDepartmentItem() {
  const name = newDepartmentName.value.trim();
  if (!name || departmentsLoading.value) {
    return;
  }

  departmentsLoading.value = true;
  departmentsError.value = "";

  try {
    const response = await fetch(`${API_BASE}/admin/departments`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include",
      body: JSON.stringify({ name }),
    });

    if (!response.ok) {
      throw new Error(await responseError(response, `Create department failed with status ${response.status}`));
    }

    newDepartmentName.value = "";
    await loadDepartments();
  } catch (err) {
    departmentsError.value = err.message || "Create department failed";
  } finally {
    departmentsLoading.value = false;
  }
}

async function deleteDepartmentItem(departmentId) {
  if (departmentsLoading.value) {
    return;
  }

  departmentsLoading.value = true;
  departmentsError.value = "";

  try {
    const response = await fetch(`${API_BASE}/admin/departments/${encodeURIComponent(departmentId)}`, {
      method: "DELETE",
      credentials: "include",
    });

    if (!response.ok) {
      throw new Error(await responseError(response, `Delete department failed with status ${response.status}`));
    }

    await loadDepartments();
    if (!departments.value.some((department) => department.name === newUserDepartment.value)) {
      newUserDepartment.value = "";
    }
    if (!departments.value.some((department) => department.name === knowledgeDepartment.value)) {
      knowledgeDepartment.value = "";
    }
  } catch (err) {
    departmentsError.value = err.message || "Delete department failed";
  } finally {
    departmentsLoading.value = false;
  }
}

async function pollKnowledgeIndexJob(jobId) {
  if (!jobId) {
    return;
  }

  for (let attempt = 0; attempt < 120; attempt += 1) {
    const response = await fetch(`${API_BASE}/knowledge/index-jobs/${encodeURIComponent(jobId)}`, {
      credentials: "include",
    });

    if (!response.ok) {
      throw new Error(`Index job polling failed with status ${response.status}`);
    }

    const data = await response.json();
    knowledgeIndexJob.value = data;

    if (data.status === "completed") {
      await loadKnowledgeDocuments();
      await loadRagStatus();
      return;
    }

    if (data.status === "failed") {
      throw new Error(data.error || "Indexing failed");
    }

    await new Promise((resolve) => window.setTimeout(resolve, 1000));
  }

  throw new Error("Indexing is taking too long, please check again later.");
}

async function pollKnowledgeIndexJobs(jobs) {
  const jobIds = (jobs || []).map((job) => job.job_id).filter(Boolean);
    if (jobIds.length === 0) {
      await loadKnowledgeSources();
      await loadKnowledgeDocuments();
      await loadRagStatus();
      return;
    }

  for (let attempt = 0; attempt < 120; attempt += 1) {
    const responses = await Promise.all(
      jobIds.map((jobId) =>
        fetch(`${API_BASE}/knowledge/index-jobs/${encodeURIComponent(jobId)}`, {
          credentials: "include",
        }).then((response) => {
          if (!response.ok) {
            throw new Error(`Index job polling failed with status ${response.status}`);
          }
          return response.json();
        }),
      ),
    );

    const completed = responses.filter((job) => job.status === "completed").length;
    const failed = responses.filter((job) => job.status === "failed").length;
    const running = responses.length - completed - failed;
    knowledgeIndexJob.value = {
      status: running > 0 ? "running" : failed > 0 ? "failed" : "completed",
      document_id: `${completed} completed, ${failed} failed, ${running} running`,
    };

    if (completed + failed === responses.length) {
      await loadKnowledgeSources();
      await loadKnowledgeDocuments();
      await loadRagStatus();
      if (failed > 0) {
        throw new Error(`${failed} index job(s) failed`);
      }
      return;
    }

    await new Promise((resolve) => window.setTimeout(resolve, 1000));
  }

  throw new Error("Indexing is taking too long, please check again later.");
}

async function deleteKnowledgeDocument(documentId) {
  if (knowledgeLoading.value) {
    return;
  }

  knowledgeLoading.value = true;
  knowledgeError.value = "";

  try {
    const response = await fetch(
      `${API_BASE}/knowledge/documents/${encodeURIComponent(documentId)}`,
      {
        method: "DELETE",
        credentials: "include",
      },
    );

    if (!response.ok) {
      throw new Error(`Delete failed with status ${response.status}`);
    }

    await loadKnowledgeDocuments();
    await loadRagStatus();
  } catch (err) {
    knowledgeError.value = err.message || "Delete failed";
  } finally {
    knowledgeLoading.value = false;
  }
}

async function reindexAllKnowledgeDocuments() {
  if (knowledgeLoading.value) {
    return;
  }

  knowledgeLoading.value = true;
  knowledgeError.value = "";
  knowledgeIndexJob.value = null;

  try {
    const response = await fetch(`${API_BASE}/knowledge/reindex`, {
      method: "POST",
      credentials: "include",
    });

    if (!response.ok) {
      throw new Error(
        await responseError(response, `Batch reindex failed with status ${response.status}`),
      );
    }

    const data = await response.json();
    knowledgeIndexJob.value = {
      status: "queued",
      document_id: `${data.queued_count} documents queued, ${data.skipped_count} skipped`,
    };
    await loadKnowledgeDocuments();
    await loadRagStatus();
  } catch (err) {
    knowledgeError.value = err.message || "Batch reindex failed";
  } finally {
    knowledgeLoading.value = false;
  }
}

async function syncKnowledgeSource(sourceId) {
  const response = await fetch(`${API_BASE}/knowledge/sources/${sourceId}/sync`, {
    method: "POST",
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(
      await responseError(response, `Source sync failed with status ${response.status}`),
    );
  }

  return response.json();
}

async function syncEnabledKnowledgeSources() {
  if (knowledgeLoading.value) {
    return;
  }

  const enabledSources = knowledgeSources.value.filter((source) => source.enabled);
  if (enabledSources.length === 0) {
    return;
  }

  knowledgeLoading.value = true;
  knowledgeError.value = "";
  knowledgeIndexJob.value = null;

  try {
    let queuedCount = 0;
    let unchangedCount = 0;
    let missingCount = 0;
    const jobs = [];
    for (const source of enabledSources) {
      const data = await syncKnowledgeSource(source.id);
      queuedCount += Number(data.queued_count || 0);
      unchangedCount += Number(data.unchanged_count || 0);
      missingCount += Number(data.missing_count || 0);
      jobs.push(...(data.jobs || []));
    }
    knowledgeIndexJob.value = {
      status: "queued",
      document_id: `${queuedCount} source files queued, ${unchangedCount} unchanged, ${missingCount} missing`,
    };
    await pollKnowledgeIndexJobs(jobs);
  } catch (err) {
    knowledgeError.value = err.message || "Source sync failed";
  } finally {
    knowledgeLoading.value = false;
  }
}

async function clearMissingKnowledgeFiles() {
  if (knowledgeLoading.value) {
    return;
  }

  knowledgeLoading.value = true;
  knowledgeError.value = "";

  try {
    const response = await fetch(`${API_BASE}/knowledge/sources/missing-files`, {
      method: "DELETE",
      credentials: "include",
    });

    if (!response.ok) {
      throw new Error(
        await responseError(response, `Clear missing files failed with status ${response.status}`),
      );
    }

    await loadKnowledgeSources();
    await loadRagStatus();
  } catch (err) {
    knowledgeError.value = err.message || "Clear missing files failed";
  } finally {
    knowledgeLoading.value = false;
  }
}

async function deduplicateKnowledgeDocuments() {
  if (knowledgeLoading.value) {
    return;
  }

  knowledgeLoading.value = true;
  knowledgeError.value = "";
  knowledgeIndexJob.value = null;

  try {
    const response = await fetch(`${API_BASE}/knowledge/documents/deduplicate`, {
      method: "POST",
      credentials: "include",
    });

    if (!response.ok) {
      throw new Error(
        await responseError(response, `Deduplicate failed with status ${response.status}`),
      );
    }

    const data = await response.json();
    knowledgeIndexJob.value = {
      status: "completed",
      document_id: `${data.removed_count || 0} duplicate document(s) removed`,
    };
    await loadKnowledgeSources();
    await loadKnowledgeDocuments();
    await loadRagStatus();
  } catch (err) {
    knowledgeError.value = err.message || "Deduplicate failed";
  } finally {
    knowledgeLoading.value = false;
  }
}

async function searchKnowledge() {
  const query = knowledgeSearchQuery.value.trim();

  if (!query || knowledgeSearchLoading.value) {
    return;
  }

  knowledgeSearchLoading.value = true;
  knowledgeSearchError.value = "";

  try {
    const response = await fetch(`${API_BASE}/knowledge/search`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include",
      body: JSON.stringify({
        query,
        top_k: defaultKnowledgeTopK(),
        min_score: defaultKnowledgeMinScore(),
      }),
    });

    if (!response.ok) {
      throw new Error(
        await responseError(response, `Search failed with status ${response.status}`),
      );
    }

    const data = await response.json();
    knowledgeSearchResults.value = data.results || [];
    await loadKnowledgeAudits();
    await loadRagStatus();
  } catch (err) {
    knowledgeSearchError.value = err.message || "Search failed";
    knowledgeSearchResults.value = [];
  } finally {
    knowledgeSearchLoading.value = false;
  }
}

async function submitFeedback(message, index, feedbackType) {
  if (!message || message.feedbackLoading || message.feedbackSent) {
    return;
  }

  message.feedbackLoading = true;
  message.feedbackError = "";

  try {
    const previousUserMessage = [...messages.value]
      .slice(0, index)
      .reverse()
      .find((item) => item.role === "user");
    const response = await fetch(`${API_BASE}/feedback`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include",
      body: JSON.stringify({
        feedback_type: feedbackType,
        conversation_id: currentConversationId.value,
        message_id: message.id || null,
        query: previousUserMessage?.content || "",
        answer: message.content || "",
        sources: message.sources || [],
      }),
    });

    if (!response.ok) {
      throw new Error(await responseError(response, `Feedback failed with status ${response.status}`));
    }

    const data = await response.json();
    if (data.message_id) {
      message.id = data.message_id;
    }
    message.feedbackSent = feedbackType;
    cacheCurrentConversation();
    if (isAdmin.value) {
      await loadRagFeedback();
      await loadRagStatus();
    }
  } catch (err) {
    message.feedbackError = err.message || "Feedback failed";
  } finally {
    message.feedbackLoading = false;
  }
}

function formatDepartments(departments) {
  const values = Array.isArray(departments) ? departments.filter(Boolean) : [];
  return values.length ? values.join(", ") : "No departments";
}

function formatAuditScope(audit) {
  const scope = audit?.scope || {};
  if (scope.is_admin || scope.role === "admin") {
    return "Scope: all departments";
  }
  return `Scope: ${formatDepartments(scope.departments || [])}`;
}

function auditStats(audit) {
  return audit?.access_stats || {};
}

function auditFilteredCount(audit) {
  return Number(auditStats(audit).access_filtered_count || 0);
}

function auditInactiveFilteredCount(audit) {
  return Number(auditStats(audit).inactive_filtered_count || 0);
}

function auditOlderVersionFilteredCount(audit) {
  return Number(auditStats(audit).older_version_filtered_count || 0);
}

function auditCandidateCount(audit) {
  return Number(auditStats(audit).candidate_count || 0);
}

function auditKeptCount(audit) {
  return Number(auditStats(audit).kept_count || 0);
}

function auditSourceDepartment(source) {
  return source?.metadata?.department || source?.department || "Public";
}

function auditSourceGroups(audit) {
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

function auditChunkLabel(source) {
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
  return parts.join(" · ");
}

function formatScore(score) {
  return Number(score || 0).toFixed(3);
}

function formatPageRange(item) {
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

function itemMetadata(item) {
  return item?.metadata || {};
}

function formatStructureLocation(item) {
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

function formatLifecycle(document) {
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

function lifecycleClass(document) {
  return {
    active: formatLifecycle(document) === "active",
    inactive: formatLifecycle(document) !== "active",
  };
}

function formatSourceName(documentId) {
  const value = String(documentId || "").trim();
  if (!value) {
    return "Unknown source";
  }
  if (value.includes("__")) {
    return value.split("__").filter(Boolean).pop() || value;
  }
  return value;
}

function formatFileSize(bytes) {
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

function decodeSourcesHeader(value) {
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

function hasSources(message) {
  return Array.isArray(message.sources);
}

function normalizeMessages(rawMessages) {
  const normalized = (rawMessages || []).map((message) => ({
    id: message.id,
    role: message.role,
    content: message.content,
    sources: message.sources,
    created_at: message.created_at,
    feedbackSent: message.feedbackSent,
    feedbackError: message.feedbackError,
  }));

  return normalized.length > 0 ? normalized : [emptyMessage];
}

function cloneMessages(rawMessages) {
  return rawMessages.map((message) => ({
    id: message.id,
    role: message.role,
    content: message.content,
    sources: Array.isArray(message.sources) ? [...message.sources] : message.sources,
    created_at: message.created_at,
    feedbackSent: message.feedbackSent,
    feedbackError: message.feedbackError,
  }));
}

function cacheCurrentConversation() {
  if (!currentConversationId.value) {
    return;
  }

  conversationMessagesCache.set(currentConversationId.value, cloneMessages(messages.value));
}

function formatDate(value) {
  if (!value) {
    return "";
  }

  return new Date(value).toLocaleString();
}

async function restoreConversation() {
  const savedId = Number(localStorage.getItem("currentConversationId"));
  if (!savedId || !conversations.value.some((conversation) => conversation.id === savedId)) {
    newConversation();
    return;
  }

  await selectConversation(savedId);
}

function newConversation() {
  currentConversationId.value = null;
  localStorage.removeItem("currentConversationId");
  messages.value = [emptyMessage];
}

function openNewChat() {
  activeView.value = "chat";
  newConversation();
}

async function scrollMessagesToBottom() {
  await nextTick();

  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
  }
}

async function selectConversation(conversationId) {
  error.value = "";
  const selectedId = Number(conversationId);

  if (currentConversationId.value === selectedId && messages.value.length > 0) {
    await scrollMessagesToBottom();
    return;
  }

  if (conversationMessagesCache.has(selectedId)) {
    currentConversationId.value = selectedId;
    localStorage.setItem("currentConversationId", String(selectedId));
    messages.value = cloneMessages(conversationMessagesCache.get(selectedId));
    await scrollMessagesToBottom();
    return;
  }

  currentConversationId.value = selectedId;
  localStorage.setItem("currentConversationId", String(selectedId));
  messages.value = [];
  conversationLoading.value = true;
  const loadToken = conversationLoadToken + 1;
  conversationLoadToken = loadToken;
  await scrollMessagesToBottom();

  try {
    const response = await fetch(`${API_BASE}/conversations/${selectedId}/messages`, {
      credentials: "include",
    });

    if (!response.ok) {
      throw new Error(`Failed to load messages with status ${response.status}`);
    }

    const data = await response.json();
    if (loadToken !== conversationLoadToken) {
      return;
    }

    messages.value = normalizeMessages(data.messages);
    conversationMessagesCache.set(selectedId, cloneMessages(messages.value));

    await scrollMessagesToBottom();
  } catch (err) {
    if (loadToken === conversationLoadToken) {
      error.value = err.message || "Failed to load conversation";
    }
  } finally {
    if (loadToken === conversationLoadToken) {
      conversationLoading.value = false;
    }
  }
}

async function openConversation(conversationId) {
  activeView.value = "chat";
  await selectConversation(conversationId);
}

async function sendMessage() {
  const text = input.value.trim();

  if (!text || loading.value) {
    return;
  }

  messages.value.push({ role: "user", content: text, created_at: new Date().toISOString() });
  input.value = "";
  error.value = "";
  loading.value = true;
  await scrollMessagesToBottom();

  try {
    const response = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include",
      body: JSON.stringify({
        message: text,
        conversation_id: currentConversationId.value,
      }),
    });

    if (!response.ok) {
      if (response.status === 404) {
        throw new Error("Chat job API is unavailable. Restart the backend service and try again.");
      }
      throw new Error(`Request failed with status ${response.status}`);
    }

    const data = await response.json();
    currentConversationId.value = data.conversation_id;
    localStorage.setItem("currentConversationId", String(data.conversation_id));
    messages.value.push({
      role: "assistant",
      content: data.answer || "",
      sources: data.sources || [],
      created_at: new Date().toISOString(),
    });
    await scrollMessagesToBottom();
    await loadConversations();
    cacheCurrentConversation();
  } catch (err) {
    error.value = err.message || "Request failed";
  } finally {
    loading.value = false;
  }
}

async function sendMessageStream() {
  const text = input.value.trim();

  if (!text || loading.value) {
    return;
  }

  messages.value.push({ role: "user", content: text, created_at: new Date().toISOString() });
  const assistantIndex = messages.value.length;
  messages.value.push({ role: "assistant", content: "", sources: [], created_at: new Date().toISOString() });
  input.value = "";
  error.value = "";
  loading.value = true;
  await scrollMessagesToBottom();

  try {
    const response = await fetch(`${API_BASE}/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include",
      body: JSON.stringify({
        message: text,
        conversation_id: currentConversationId.value,
      }),
    });

    if (!response.ok) {
      throw new Error(`Request failed with status ${response.status}`);
    }

    const conversationId = Number(response.headers.get("X-Conversation-Id"));
    if (conversationId) {
      currentConversationId.value = conversationId;
      localStorage.setItem("currentConversationId", String(conversationId));
      await loadConversations();
    }

    messages.value[assistantIndex].sources = decodeSourcesHeader(
      response.headers.get("X-Knowledge-Sources"),
    );

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error("Streaming response is not available.");
    }

    const decoder = new TextDecoder();
    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        break;
      }

      messages.value[assistantIndex].content += decoder.decode(value, { stream: true });
      await scrollMessagesToBottom();
    }

    const tail = decoder.decode();
    if (tail) {
      messages.value[assistantIndex].content += tail;
      await scrollMessagesToBottom();
    }

    cacheCurrentConversation();
    await loadConversations();
    await loadDeepseekBalance();
  } catch (err) {
    messages.value[assistantIndex].content ||= err.message || "Request failed";
    error.value = err.message || "Request failed";
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  document.addEventListener("pointerdown", onDocumentPointerDown);
});

onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", onDocumentPointerDown);
  stopRagStatusRefresh();
});

checkSession();
</script>

<template>
  <main class="app-shell">
    <section class="chat-panel">
      <header class="toolbar">
        <div>
          <h1>RAG</h1>
          <p>{{ isAuthenticated ? "AI agent" : "Sign in to continue" }}</p>
        </div>
        <div class="session">
          <span
            v-if="isAuthenticated && isAdmin"
            class="chat-capacity-status"
            title="Active chats / chat limit"
          >
            {{ chatAdmissionLabel }}
          </span>
          <span
            v-if="isAuthenticated && isAdmin"
            class="balance-status"
            :class="{ unavailable: balanceError || deepseekBalance?.is_available === false }"
          >
            {{ formatDeepseekBalance() }}
          </span>
          <details v-if="isAuthenticated" ref="settingsMenu" class="settings-menu">
            <summary class="status" title="Account menu" aria-label="Account menu">
              {{ currentUser }}
            </summary>
            <div class="settings-menu-panel">
              <button
                v-if="isAdmin"
                type="button"
                :class="{ active: activeView === 'knowledge' }"
                @click="activeView = 'knowledge'; closeSettingsMenu()"
              >
                Knowledge
              </button>
              <button
                v-if="isAdmin"
                type="button"
                :class="{ active: activeView === 'users' }"
                @click="activeView = 'users'; closeSettingsMenu()"
              >
                Users
              </button>
              <button
                v-if="isAdmin"
                type="button"
                :class="{ active: activeView === 'operations' }"
                @click="activeView = 'operations'; openOperationsOverview(); closeSettingsMenu()"
              >
                Operations
              </button>
              <button
                class="logout-menu-button"
                type="button"
                :disabled="authLoading"
                @click="closeSettingsMenu(); logout()"
              >
                Logout
              </button>
            </div>
          </details>
        </div>
      </header>

      <div v-if="!isAuthenticated" class="login-view">
        <div class="login-copy">
          <p class="eyebrow">Secure access</p>
          <h2>Open your agent workspace</h2>
          <p>Use your server account to continue.</p>
        </div>

        <form class="login-form" @submit.prevent="login">
          <label>
            <span>Username</span>
            <input v-model="username" autocomplete="username" placeholder="admin" />
          </label>
          <label>
            <span>Password</span>
            <input
              v-model="password"
              type="password"
              autocomplete="current-password"
              placeholder="Enter password"
            />
          </label>
          <button type="submit" :disabled="authLoading || !username.trim() || !password">
            {{ authLoading ? "Signing in" : "Sign in" }}
          </button>
        </form>
      </div>

      <div v-else class="workspace">
        <aside class="sidebar">
          <button class="new-chat-button" type="button" @click="openNewChat">
            New chat
          </button>
          <div class="conversation-list">
            <button
              v-for="conversation in conversations"
              :key="conversation.id"
              class="conversation-item"
              :class="{ active: conversation.id === currentConversationId }"
              type="button"
              @click="openConversation(conversation.id)"
            >
              <div class="conversation-title">{{ conversation.title }}</div>
              <div v-if="conversation.updated_at" class="conversation-time">{{ formatDate(conversation.updated_at) }}</div>
            </button>
          </div>
        </aside>

        <div v-if="activeView === 'chat'" class="chat-column">
          <div ref="messagesContainer" class="messages">
            <div v-if="conversationLoading" class="message-skeleton-list" aria-hidden="true">
              <div class="message-skeleton">
                <span></span>
                <strong></strong>
                <em></em>
              </div>
              <div class="message-skeleton user">
                <span></span>
                <strong></strong>
              </div>
              <div class="message-skeleton">
                <span></span>
                <strong></strong>
                <em></em>
              </div>
            </div>
            <article
              v-if="!conversationLoading"
              v-for="(message, index) in messages"
              :key="index"
              class="message"
              :class="message.role"
            >
              <div class="message-header">
                <span class="role">{{ message.role }}</span>
                <span v-if="message.created_at" class="message-time">{{ formatDate(message.created_at) }}</span>
              </div>
              <pre>{{ message.content }}</pre>
              <div
                v-if="message.role === 'assistant' && message.content && index > 0"
                class="message-feedback"
              >
                <button
                  v-for="type in feedbackOptions(message)"
                  :key="type"
                  class="feedback-button"
                  type="button"
                  :disabled="message.feedbackLoading"
                  @click="submitFeedback(message, index, type)"
                >
                  {{ feedbackTypeLabel(type) }}
                </button>
                <span v-if="message.feedbackSent" class="feedback-saved">
                  Saved: {{ feedbackTypeLabel(message.feedbackSent) }}
                </span>
                <span v-if="message.feedbackError" class="feedback-error">
                  {{ message.feedbackError }}
                </span>
              </div>
              <div
                v-if="message.role === 'assistant' && hasSources(message)"
                class="message-sources"
              >
                <div v-if="message.sources.length" class="source-list">
                  <details
                    v-for="source in message.sources"
                    :key="source.chunk_id || `${source.document_id}-${source.chunk_index}`"
                    class="source-item"
                  >
                    <summary>
                      <span class="source-label">[{{ source.label }}]</span>
                      <span class="source-document" :title="source.document_id || ''">
                        {{ formatSourceName(source.document_id) }}
                      </span>
                      <span class="source-meta">
                        chunk {{ source.chunk_index }} · score {{ formatScore(source.score) }}
                      </span>
                      <span class="source-meta-readable">
                        chunk {{ source.chunk_index }}
                        <template v-if="formatPageRange(source)"> · {{ formatPageRange(source) }}</template>
                        · score {{ formatScore(source.score) }}
                      </span>
                      <span class="source-meta-clean">
                        chunk {{ source.chunk_index }}
                        <template v-if="formatPageRange(source)"> | {{ formatPageRange(source) }}</template>
                        | score {{ formatScore(source.score) }}
                      </span>
                    </summary>
                    <p>{{ source.text }}</p>
                  </details>
                </div>
                <p v-else-if="message.content" class="source-empty">
                  本回答未使用知识库来源
                </p>
              </div>
            </article>
          </div>

          <p v-if="error" class="error">{{ error }}</p>

          <form class="composer" @submit.prevent="sendMessageStream">
            <textarea
              v-model="input"
              rows="3"
              placeholder="Type a message..."
              :disabled="conversationLoading"
              @keydown.enter.exact.prevent="sendMessageStream"
            />
            <button type="submit" :disabled="loading || conversationLoading || !input.trim()">
              {{ loading ? "Sending" : "Send" }}
            </button>
          </form>
        </div>

        <div v-else-if="isAdmin && activeView === 'knowledge'" class="knowledge-column">
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
                  :disabled="knowledgeLoading || knowledgeDocuments.length === 0"
                  @click="reindexAllKnowledgeDocuments"
                >
                  Reindex all
                </button>
                <button
                  class="secondary-button"
                  type="button"
                  :disabled="knowledgeLoading || !hasEnabledKnowledgeSources"
                  @click="syncEnabledKnowledgeSources"
                >
                  Sync now
                </button>
                <button
                  class="secondary-button"
                  type="button"
                  :disabled="knowledgeLoading || knowledgeDocuments.length < 2"
                  @click="deduplicateKnowledgeDocuments"
                >
                  Deduplicate
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
                <span class="rag-status-badge" :class="ragStatusClass()">
                  {{ ragStatus.status }}
                </span>
                <span>{{ ragStatus.documents?.count || 0 }} docs</span>
                <span>{{ ragStatus.documents?.chunk_count || 0 }} chunks</span>
                <span>{{ ragStatus.sources?.enabled_count || 0 }} active sources</span>
              </div>
              <div class="rag-metric-grid">
                <div>
                  <strong>{{ formatStatusCount(ragStatus.index_jobs?.status_counts, "failed") }}</strong>
                  <span>failed jobs</span>
                </div>
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
                  <strong>{{ ragStatus.feedback?.negative || 0 }}</strong>
                  <span>negative feedback</span>
                </div>
                <div>
                  <strong>{{ ragStatus.feedback?.positive || 0 }}</strong>
                  <span>useful feedback</span>
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
              <ul v-if="ragStatus.issues?.length" class="rag-issue-list">
                <li v-for="issue in ragStatus.issues" :key="issue.name">
                  {{ issue.message }}
                </li>
              </ul>
            </div>

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
                :class="{ active: knowledgeTab === 'evaluation' }"
                @click="setKnowledgeTab('evaluation')"
              >
                Answer Quality
              </button>
            </div>

            <template v-if="knowledgeTab === 'documents'">
            <form class="index-form" @submit.prevent="uploadKnowledgeFile">
              <input
                ref="knowledgeFileInput"
                class="hidden-file-input"
                type="file"
                accept=".md,.pdf,.docx,.csv,.xlsx,.xls,text/markdown,application/pdf"
                @change="onKnowledgeFileChange"
              />
              <label class="notes-field">
                <span>Notes</span>
                <textarea
                  v-model="knowledgeNotes"
                  rows="1"
                  placeholder="Optional context for this document"
                />
              </label>
              <label>
                <span>Department</span>
                <select v-model="knowledgeDepartment">
                  <option value="">Public</option>
                  <option
                    v-for="department in departments"
                    :key="department.id"
                    :value="department.name"
                  >
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
                <button class="secondary-button file-button" type="button" @click="chooseKnowledgeFile">
                  Browse
                </button>
                <button type="submit" :disabled="knowledgeLoading || !selectedKnowledgeFile">
                  {{ knowledgeLoading ? "Uploading" : "Upload" }}
                </button>
              </div>
            </form>

            <p v-if="knowledgeError" class="error knowledge-error">{{ knowledgeError }}</p>
            <p v-if="knowledgeIndexJob && knowledgeIndexJob.status !== 'completed'" class="knowledge-status">
              {{
                knowledgeIndexJob.status === "failed"
                  ? `Index failed: ${knowledgeIndexJob.error || "unknown error"}`
                  : `Index job ${knowledgeIndexJob.status}: ${knowledgeIndexJob.document_id || knowledgeIndexJob.path || knowledgeIndexJob.job_id}`
              }}
            </p>

            <form class="knowledge-search-form" @submit.prevent="searchKnowledge">
              <label>
                <span>Search test</span>
                <input
                  v-model="knowledgeSearchQuery"
                  placeholder="Test a question against indexed knowledge"
                />
              </label>
              <button type="submit" :disabled="knowledgeSearchLoading || !knowledgeSearchQuery.trim()">
                {{ knowledgeSearchLoading ? "Searching" : "Search" }}
              </button>
            </form>

            <p v-if="knowledgeSearchError" class="error knowledge-error">
              {{ knowledgeSearchError }}
            </p>

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

            <div class="document-list">
              <article
                v-for="document in knowledgeDocuments"
                :key="document.document_id"
                class="document-item"
              >
                <div>
                  <h3>{{ document.file_name || document.document_id }}</h3>
                  <p>
                    {{ document.chunk_count }} chunks
                    <span v-if="document.updated_at"> · {{ formatDate(document.updated_at) }}</span>
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

              <p v-if="knowledgeDocuments.length === 0" class="empty-state">
                No indexed documents.
              </p>
            </div>
            </template>

            <template v-else>
            <div class="audit-header">
              <div>
                <h3>Answer Quality</h3>
                <p>Latest benchmark report and retrieval quality signals.</p>
              </div>
              <div class="eval-actions">
                <select v-model="selectedRagEvalSuite" :disabled="ragEvalRunning">
                  <option
                    v-for="suite in ragEvalSuites"
                    :key="suite.id"
                    :value="suite.id"
                  >
                    {{ suite.name }} - {{ suite.question_count }}
                  </option>
                </select>
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
                  <strong>{{ Number(ragEval.summary?.mrr || 0).toFixed(3) }}</strong>
                  <span>MRR</span>
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
              <div v-if="ragEval.failed_rows?.length" class="eval-failure-list">
                <article v-for="row in ragEval.failed_rows.slice(0, 5)" :key="row.id || row.question">
                  <strong>{{ row.id || row.category || "case" }}</strong>
                  <p>{{ row.question }}</p>
                  <span>
                    expected {{ row.expected_docs || "no source" }} | top {{ formatSourceName(row.top_document) || "none" }} | score {{ formatScore(row.top_score) }}
                  </span>
                </article>
              </div>
            </div>
            <p v-else-if="!ragEvalLoading" class="empty-state eval-empty">
              No evaluation report found. Run the RAG evaluation script to populate this panel.
            </p>
            </template>
          </section>
        </div>

        <div v-else-if="isAdmin && activeView === 'users'" class="users-column">
          <section class="users-section">
            <div class="section-header">
              <div>
                <h2>{{ usersTab === "departments" ? "Departments" : "Users" }}</h2>
                <p>
                  {{
                    usersTab === "departments"
                      ? "Maintain the department options used by users and knowledge files."
                      : "Create accounts and choose who can manage the workspace."
                  }}
                </p>
              </div>
            </div>

            <div class="operations-tabs" role="tablist" aria-label="User management sections">
              <button
                type="button"
                :class="{ active: usersTab === 'users' }"
                @click="setUsersTab('users')"
              >
                Users
              </button>
              <button
                type="button"
                :class="{ active: usersTab === 'departments' }"
                @click="setUsersTab('departments')"
              >
                Departments
              </button>
            </div>

            <template v-if="usersTab === 'users'">
            <form class="user-form" @submit.prevent="createUserAccount">
              <label>
                <span>Username</span>
                <input v-model="newUserUsername" autocomplete="off" placeholder="employee.name" />
              </label>
              <label>
                <span>Password</span>
                <input
                  v-model="newUserPassword"
                  type="password"
                  autocomplete="new-password"
                  placeholder="At least 12 characters"
                />
              </label>
              <label>
                <span>Role</span>
                <select v-model="newUserRole">
                  <option value="user">user</option>
                  <option value="admin">admin</option>
                </select>
              </label>
              <label>
                <span>Departments</span>
                <select
                  v-model="newUserDepartment"
                  :disabled="newUserRole === 'admin'"
                >
                  <option value="">
                    {{ newUserRole === "admin" ? "All departments" : "Select department" }}
                  </option>
                  <option
                    v-for="department in departments"
                    :key="department.id"
                    :value="department.name"
                  >
                    {{ department.name }}
                  </option>
                </select>
              </label>
              <button
                type="submit"
                :disabled="usersLoading || !newUserUsername.trim() || !newUserPassword || (newUserRole === 'user' && !newUserDepartment)"
              >
                {{ usersLoading ? "Creating" : "Create" }}
              </button>
            </form>

            <p v-if="usersError" class="error users-error">{{ usersError }}</p>

            <div class="user-list">
              <article v-for="user in users" :key="user.id" class="user-item">
                <div>
                  <h3>{{ user.username }}</h3>
                  <p>{{ user.created_at ? formatDate(user.created_at) : "Created" }}</p>
                  <p class="user-departments">
                    {{ user.role === "admin" ? "All departments" : formatDepartments(user.departments) }}
                  </p>
                </div>
                <div v-if="userEdits[user.id]" class="user-edit-controls">
                  <select v-model="userEdits[user.id].role">
                    <option value="user">user</option>
                    <option value="admin">admin</option>
                  </select>
                  <select
                    v-model="userEdits[user.id].department"
                    :disabled="userEdits[user.id].role === 'admin'"
                  >
                    <option value="">
                      {{ userEdits[user.id].role === "admin" ? "All departments" : "Select department" }}
                    </option>
                    <option
                      v-for="department in departments"
                      :key="department.id"
                      :value="department.name"
                    >
                      {{ department.name }}
                    </option>
                  </select>
                  <button
                    class="secondary-button"
                    type="button"
                    :disabled="usersLoading || !userEditChanged(user)"
                    @click="saveUserAccount(user)"
                  >
                    Save
                  </button>
                </div>
              </article>

              <p v-if="users.length === 0 && !usersLoading" class="empty-state">
                No users found.
              </p>
            </div>
            </template>

            <template v-else>
            <form class="department-form" @submit.prevent="createDepartmentItem">
              <label>
                <span>Name</span>
                <input
                  v-model="newDepartmentName"
                  autocomplete="off"
                  placeholder="Finance"
                />
              </label>
              <button
                type="submit"
                :disabled="departmentsLoading || !newDepartmentName.trim()"
              >
                {{ departmentsLoading ? "Saving" : "Add" }}
              </button>
            </form>

            <p v-if="departmentsError" class="error users-error">{{ departmentsError }}</p>

            <div class="department-list">
              <article
                v-for="department in departments"
                :key="department.id"
                class="department-item"
              >
                <div>
                  <h3>{{ department.name }}</h3>
                  <p>{{ department.created_at ? formatDate(department.created_at) : "Created" }}</p>
                </div>
                <button
                  class="danger-button"
                  type="button"
                  :disabled="departmentsLoading"
                  @click="deleteDepartmentItem(department.id)"
                >
                  Delete
                </button>
              </article>

              <p v-if="departments.length === 0 && !departmentsLoading" class="empty-state">
                No departments yet.
              </p>
            </div>
            </template>

          </section>
        </div>

        <div v-else-if="isAdmin && activeView === 'operations'" class="users-column">
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
                  <div>
                    <strong>{{ ragFeedbackSummary?.total || 0 }}</strong>
                    <span>total</span>
                  </div>
                  <div>
                    <strong>{{ ragFeedbackSummary?.positive || 0 }}</strong>
                    <span>useful</span>
                  </div>
                  <div>
                    <strong>{{ ragFeedbackSummary?.negative || 0 }}</strong>
                    <span>needs work</span>
                  </div>
                  <div>
                    <strong>{{ ragFeedbackSummary?.by_type?.wrong_source || 0 }}</strong>
                    <span>wrong source</span>
                  </div>
                  <button
                    class="metric-button"
                    type="button"
                    :disabled="(ragFeedbackSummary?.by_type?.missing_doc || 0) === 0"
                    @click="openMissingDocManagement"
                  >
                    <strong>{{ ragFeedbackSummary?.by_type?.missing_doc || 0 }}</strong>
                    <span>missing doc</span>
                  </button>
                </div>
                <div v-if="ragFeedback.length" class="feedback-list">
                  <article v-for="item in pagedRagFeedback" :key="item.id" class="feedback-item">
                    <div class="audit-title">
                      <strong>{{ item.username }}</strong>
                      <span>{{ feedbackTypeLabel(item.feedback_type) }}</span>
                      <span>{{ formatDate(item.created_at) }}</span>
                    </div>
                    <p>{{ item.query || item.answer || "No question captured." }}</p>
                    <p class="audit-meta">
                      <span>{{ item.sources?.length || 0 }} sources</span>
                      <span v-if="item.conversation_id">conversation {{ item.conversation_id }}</span>
                      <span v-if="item.sources?.[0]">{{ formatSourceName(item.sources[0].document_id) }}</span>
                    </p>
                  </article>
                </div>
                <div v-if="ragFeedback.length > pageSize" class="pagination">
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
                <p v-if="ragFeedback.length === 0 && !feedbackLoading" class="empty-state">
                  No answer feedback yet.
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
                        <small>{{ group.department }} · {{ group.sources.length }} chunks</small>
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
                  <p v-if="item.answer" class="audit-answer">{{ item.answer }}</p>
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

      </div>

      <p v-if="!isAuthenticated && error" class="error">{{ error }}</p>
    </section>
  </main>
</template>

<style scoped>
.message-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.message-time {
  font-size: 12px;
  color: #888;
}

.conversation-item {
  text-align: left;
}

.conversation-title {
  font-weight: 500;
  margin-bottom: 4px;
}

.conversation-time {
  font-size: 11px;
  color: #888;
}
</style>
