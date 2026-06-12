function bindRef(target, key, source) {
  Object.defineProperty(target, key, {
    enumerable: true,
    get: () => source.value,
    set: (value) => {
      source.value = value;
    },
  });
}

function bindReadonly(target, key, source) {
  Object.defineProperty(target, key, {
    enumerable: true,
    get: () => source.value,
  });
}

export function createWorkspaceBindings({ refs, values, actions, helpers }) {
  const bindings = {};
  [
    "input",
    "conversations",
    "currentConversationId",
    "activeView",
    "loading",
    "conversationLoading",
    "error",
    "knowledgeLoading",
    "knowledgeDocuments",
    "ragStatus",
    "ragStatusError",
    "failedIndexJobsExpanded",
    "acknowledgingFailedJobs",
    "knowledgeTab",
    "selectedKnowledgeFile",
    "knowledgeNotes",
    "knowledgeDepartment",
    "departments",
    "knowledgeError",
    "knowledgeIndexJob",
    "knowledgeSearchQuery",
    "knowledgeSearchLoading",
    "knowledgeSearchError",
    "knowledgeSearchResults",
    "ragEvalSuites",
    "selectedRagEvalSuite",
    "ragEvalRunning",
    "ragEvalLoading",
    "ragEvalError",
    "ragEval",
    "modelUsagePeriod",
    "modelUsageError",
    "usageTrendTab",
    "usageTrendTooltip",
    "usageEventsPage",
    "usersTab",
    "newUserUsername",
    "newUserPassword",
    "newUserRole",
    "newUserDepartment",
    "usersLoading",
    "usersError",
    "users",
    "userEdits",
    "departmentsLoading",
    "departmentsError",
    "newDepartmentName",
    "operationsView",
    "operationsTab",
    "feedbackLoading",
    "feedbackError",
    "ragFeedbackSummary",
    "ragFeedback",
    "feedbackPage",
    "auditLoading",
    "auditError",
    "knowledgeAudits",
    "auditPage",
    "missingDocPage",
    "messages",
  ].forEach((key) => bindRef(bindings, key, refs[key]));

  [
    "isAdmin",
    "hasEnabledKnowledgeSources",
    "selectedRagEvalSuiteInfo",
    "usageEventsTotalPages",
    "pagedModelUsageEvents",
    "pagedRagFeedback",
    "feedbackTotalPages",
    "pagedKnowledgeAudits",
    "auditTotalPages",
    "missingDocFeedback",
    "pagedMissingDocFeedback",
    "missingDocTotalPages",
  ].forEach((key) => bindReadonly(bindings, key, refs[key]));

  bindings.chatView = refs.chatView;
  bindings.pageSize = values.pageSize;

  Object.assign(bindings, actions, helpers);
  return bindings;
}
