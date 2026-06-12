import test from "node:test";
import assert from "node:assert/strict";

import { useChatConversations } from "../useChatConversations.js";

function ref(value) {
  return { value };
}

test("openNewChat clears selected conversation and restores empty messages", () => {
  const removedKeys = [];
  const originalLocalStorage = globalThis.localStorage;
  globalThis.localStorage = {
    removeItem: (key) => removedKeys.push(key),
  };
  const refs = {
    input: ref(""),
    activeView: ref("knowledge"),
    loading: ref(false),
    conversationLoading: ref(false),
    error: ref(""),
    chatView: ref(null),
    conversations: ref([{ id: 7, title: "Old chat" }]),
    currentConversationId: ref(7),
    messages: ref([{ role: "assistant", content: "Old answer" }]),
    deepseekBalance: ref(null),
    balanceError: ref(""),
    balanceLoading: ref(false),
  };
  const emptyMessages = () => [{ role: "assistant", content: "Ready." }];
  const subject = useChatConversations({
    API_BASE: "http://api.test",
    refs,
    loaders: {
      loadConversations: async () => {},
      loadDeepseekBalance: async () => {},
    },
    helpers: {
      cloneMessages: (messages) => messages.map((message) => ({ ...message })),
      emptyMessages,
      normalizeMessages: (messages) => messages,
      decodeSourcesHeader: () => [],
    },
  });

  try {
    subject.openNewChat();
  } finally {
    globalThis.localStorage = originalLocalStorage;
  }

  assert.equal(refs.activeView.value, "chat");
  assert.equal(refs.currentConversationId.value, null);
  assert.deepEqual(refs.messages.value, emptyMessages());
  assert.deepEqual(removedKeys, ["currentConversationId"]);
});
