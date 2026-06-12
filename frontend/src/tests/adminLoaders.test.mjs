import test from "node:test";
import assert from "node:assert/strict";

import {
  activateNonAdminChat,
  loadAdminDashboard,
  resetAdminState,
} from "../adminLoaders.js";

function ref(value) {
  return { value };
}

test("loadAdminDashboard runs admin loaders in the expected order", async () => {
  const calls = [];

  await loadAdminDashboard({
    isAdmin: ref(true),
    activeView: ref("chat"),
    startRagStatusRefresh: () => calls.push("start-refresh"),
    stopRagStatusRefresh: () => calls.push("stop-refresh"),
    loaders: [
      ["sources", async () => calls.push("sources")],
      ["documents", async () => calls.push("documents")],
      ["status", async () => calls.push("status")],
    ],
  });

  assert.deepEqual(calls, ["sources", "documents", "status", "start-refresh"]);
});

test("loadAdminDashboard activates chat for non-admin users", async () => {
  const activeView = ref("operations");
  const calls = [];

  await loadAdminDashboard({
    isAdmin: ref(false),
    activeView,
    startRagStatusRefresh: () => calls.push("start-refresh"),
    stopRagStatusRefresh: () => calls.push("stop-refresh"),
    loaders: [
      ["sources", async () => calls.push("sources")],
    ],
  });

  assert.equal(activeView.value, "chat");
  assert.deepEqual(calls, ["stop-refresh"]);
});

test("activateNonAdminChat switches to chat and stops refresh", () => {
  const activeView = ref("operations");
  const calls = [];

  activateNonAdminChat({
    activeView,
    stopRagStatusRefresh: () => calls.push("stop-refresh"),
  });

  assert.equal(activeView.value, "chat");
  assert.deepEqual(calls, ["stop-refresh"]);
});

test("resetAdminState clears admin-only refs and caches", () => {
  const cache = new Map([["conversation", [{ content: "cached" }]]]);
  const state = {
    currentConversationId: ref(7),
    conversations: ref([{ id: 7 }]),
    knowledgeDocuments: ref([{ id: "doc" }]),
    knowledgeSources: ref([{ id: 1 }]),
    ragStatus: ref({ status: "ok" }),
    ragStatusError: ref("status error"),
    modelUsage: ref({ today: {} }),
    modelUsageError: ref("usage error"),
    departments: ref([{ name: "HR" }]),
    departmentsError: ref("department error"),
    newDepartmentName: ref("New"),
    users: ref([{ username: "admin" }]),
    usersError: ref("user error"),
    knowledgeAudits: ref([{ id: 1 }]),
    auditError: ref("audit error"),
    ragEval: ref({ summary: {} }),
    ragEvalError: ref("eval error"),
    ragFeedback: ref([{ id: 1 }]),
    ragFeedbackSummary: ref({ useful: 1 }),
    feedbackError: ref("feedback error"),
    deepseekBalance: ref({ balance: 1 }),
    balanceError: ref("balance error"),
    conversationMessagesCache: cache,
  };

  resetAdminState(state);

  assert.equal(state.currentConversationId.value, null);
  assert.deepEqual(state.conversations.value, []);
  assert.deepEqual(state.knowledgeDocuments.value, []);
  assert.deepEqual(state.knowledgeSources.value, []);
  assert.equal(state.ragStatus.value, null);
  assert.equal(state.ragFeedbackSummary.value, null);
  assert.equal(cache.size, 0);
});
