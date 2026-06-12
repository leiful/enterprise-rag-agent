import { loadAdminDashboard, resetAdminState } from "./adminLoaders.js";
import { emptyMessages, resolveUserRole } from "./uiHelpers.js";

export function useAuthSession({
  API_BASE,
  refs,
  loaders,
  helpers,
}) {
  const {
    username,
    password,
    currentUser,
    currentUserRole,
    conversations,
    currentConversationId,
    activeView,
    authLoading,
    error,
    settingsMenu,
    isAuthenticated,
    isAdmin,
    knowledgeDocuments,
    knowledgeSources,
    ragStatus,
    ragStatusError,
    modelUsage,
    modelUsageError,
    departments,
    departmentsError,
    newDepartmentName,
    users,
    usersError,
    knowledgeAudits,
    auditError,
    ragEval,
    ragEvalError,
    ragFeedback,
    ragFeedbackSummary,
    feedbackError,
    deepseekBalance,
    balanceError,
    messages,
  } = refs;
  const { adminDashboardLoaders, restoreConversation } = loaders;
  let ragStatusRefreshTimer = null;

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
        loaders.loadRagStatus({ silent: true });
      }
    }, 5000);
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
        await loadAdminDashboard({
          isAdmin,
          activeView,
          startRagStatusRefresh,
          stopRagStatusRefresh,
          loaders: adminDashboardLoaders(),
        });
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
      await loadAdminDashboard({
        isAdmin,
        activeView,
        startRagStatusRefresh,
        stopRagStatusRefresh,
        loaders: adminDashboardLoaders(),
      });
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
      resetAdminState({
        currentConversationId,
        conversations,
        knowledgeDocuments,
        knowledgeSources,
        ragStatus,
        ragStatusError,
        modelUsage,
        modelUsageError,
        departments,
        departmentsError,
        newDepartmentName,
        users,
        usersError,
        knowledgeAudits,
        auditError,
        ragEval,
        ragEvalError,
        ragFeedback,
        ragFeedbackSummary,
        feedbackError,
        deepseekBalance,
        balanceError,
        conversationMessagesCache: helpers.conversationMessagesCache,
      });
      messages.value = emptyMessages();
      helpers.conversationMessagesCache.clear();
      localStorage.removeItem("currentConversationId");
      password.value = "";
      authLoading.value = false;
    }
  }

  return {
    checkSession,
    closeSettingsMenu,
    loadConversations,
    login,
    logout,
    onDocumentPointerDown,
    stopRagStatusRefresh,
  };
}
