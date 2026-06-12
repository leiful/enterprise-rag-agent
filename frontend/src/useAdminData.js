import { DEFAULT_RAG_EVAL_SUITES } from "./appConfig.js";
import { totalPages } from "./pagination.js";
import {
  formatDeepseekBalance as formatDeepseekBalanceValue,
  ragStatusClass as buildRagStatusClass,
  responseError,
} from "./uiHelpers.js";

export function useAdminData({ API_BASE, refs, pageSize, missingDocFeedback }) {
  const {
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
  } = refs;

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

  async function acknowledgeFailedIndexJobs(jobIds = null) {
    acknowledgingFailedJobs.value = true;
    ragStatusError.value = "";

    try {
      const response = await fetch(`${API_BASE}/knowledge/index-jobs/acknowledge-failed`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ job_ids: jobIds }),
      });

      if (!response.ok) {
        throw new Error(await responseError(response, `Failed to acknowledge index jobs with status ${response.status}`));
      }

      await loadRagStatus({ silent: true });
    } catch (err) {
      ragStatusError.value = err.message || "Failed to acknowledge index jobs";
    } finally {
      acknowledgingFailedJobs.value = false;
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
      auditPage.value = Math.min(auditPage.value, totalPages(knowledgeAudits.value.length, pageSize));
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
      ragEvalSuites.value = [...DEFAULT_RAG_EVAL_SUITES];
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
        selectedRagEvalSuite.value = ragEvalSuites.value[0]?.id || "uploaded_pdfs";
      }
    } catch (err) {
      ragEvalSuites.value = [...DEFAULT_RAG_EVAL_SUITES];
    }
  }

  async function loadModelUsage() {
    if (!isAdmin.value) {
      modelUsage.value = null;
      return;
    }

    modelUsageLoading.value = true;
    modelUsageError.value = "";

    try {
      const response = await fetch(`${API_BASE}/admin/model-usage`, {
        credentials: "include",
      });

      if (!response.ok) {
        throw new Error(await responseError(response, `Failed to load token usage with status ${response.status}`));
      }

      modelUsage.value = await response.json();
    } catch (err) {
      modelUsageError.value = err.message || "Failed to load token usage";
    } finally {
      modelUsageLoading.value = false;
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
          skip_upload: selectedRagEvalSuite.value === "uploaded_pdfs",
          skip_search: true,
        }),
      });

      if (!response.ok) {
        throw new Error(await responseError(response, `RAG evaluation failed with status ${response.status}`));
      }

      await response.json();
      await loadRagEval();
      await loadModelUsage();
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
      feedbackPage.value = Math.min(feedbackPage.value, totalPages(ragFeedback.value.length, pageSize));
      missingDocPage.value = Math.min(missingDocPage.value, totalPages(missingDocFeedback.value.length, pageSize));
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
    return formatDeepseekBalanceValue(deepseekBalance.value, balanceLoading.value);
  }

  function ragStatusClass() {
    return buildRagStatusClass(ragStatus.value?.status || "unknown");
  }

  return {
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
  };
}
