export function activateNonAdminChat({ activeView, stopRagStatusRefresh }) {
  activeView.value = "chat";
  stopRagStatusRefresh();
}

export async function loadAdminDashboard({
  isAdmin,
  activeView,
  startRagStatusRefresh,
  stopRagStatusRefresh,
  loaders,
}) {
  if (!isAdmin.value) {
    activateNonAdminChat({ activeView, stopRagStatusRefresh });
    return;
  }

  for (const [, loader] of loaders) {
    await loader();
  }
  startRagStatusRefresh();
}

export function resetAdminState(state) {
  state.currentConversationId.value = null;
  state.conversations.value = [];
  state.knowledgeDocuments.value = [];
  state.knowledgeSources.value = [];
  state.ragStatus.value = null;
  state.ragStatusError.value = "";
  state.modelUsage.value = null;
  state.modelUsageError.value = "";
  state.departments.value = [];
  state.departmentsError.value = "";
  state.newDepartmentName.value = "";
  state.users.value = [];
  state.usersError.value = "";
  state.knowledgeAudits.value = [];
  state.auditError.value = "";
  state.ragEval.value = null;
  state.ragEvalError.value = "";
  state.ragFeedback.value = [];
  state.ragFeedbackSummary.value = null;
  state.feedbackError.value = "";
  state.deepseekBalance.value = null;
  state.balanceError.value = "";
  state.conversationMessagesCache.clear();
}
