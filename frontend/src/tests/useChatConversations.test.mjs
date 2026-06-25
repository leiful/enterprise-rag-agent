import test from "node:test";
import assert from "node:assert/strict";

import { useChatConversations } from "../useChatConversations.js";

function ref(value) {
  return { value };
}

function createSubject(overrides = {}) {
  const refs = {
    input: ref("微波炉是怎么工作的"),
    activeView: ref("chat"),
    loading: ref(false),
    conversationLoading: ref(false),
    error: ref(""),
    chatView: ref(null),
    conversations: ref([]),
    currentConversationId: ref(null),
    messages: ref([]),
    deepseekBalance: ref(null),
    balanceError: ref(""),
    balanceLoading: ref(false),
    ...overrides.refs,
  };
  const calls = {
    conversationsLoaded: 0,
    balanceLoaded: 0,
    storedItems: [],
    fetches: [],
  };
  const originalFetch = globalThis.fetch;
  const originalLocalStorage = globalThis.localStorage;

  globalThis.localStorage = {
    setItem: (key, value) => calls.storedItems.push([key, value]),
    removeItem: () => {},
    getItem: () => null,
    ...overrides.localStorage,
  };
  globalThis.fetch = overrides.fetchImpl || (async (url, options) => {
    calls.fetches.push({ url, options });
    return {
      ok: true,
      json: async () => ({
        answer: "完整答案",
        conversation_id: 42,
        sources: [{ label: "K1" }],
      }),
    };
  });

  const subject = useChatConversations({
    API_BASE: "http://api.test",
    refs,
    loaders: {
      loadConversations: async () => {
        calls.conversationsLoaded += 1;
      },
      loadDeepseekBalance: async () => {
        calls.balanceLoaded += 1;
      },
      ...overrides.loaders,
    },
    helpers: {
      cloneMessages: (messages) => messages.map((message) => ({ ...message })),
      emptyMessages: () => [{ role: "assistant", content: "Ready." }],
      normalizeMessages: (messages) => messages,
      decodeSourcesHeader: () => [],
      ...overrides.helpers,
    },
    typing: {
      delayMs: 0,
      chunkSize: 2,
      ...overrides.typing,
    },
  });

  return {
    refs,
    calls,
    subject,
    restoreGlobals() {
      globalThis.fetch = originalFetch;
      globalThis.localStorage = originalLocalStorage;
    },
  };
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

test("sendMessageWithTyping posts to stable chat endpoint and shows thinking while waiting", async () => {
  let resolveJson;
  const pendingJson = new Promise((resolve) => {
    resolveJson = resolve;
  });
  const setup = createSubject({
    fetchImpl: async (url, options) => ({
      ok: true,
      json: async () => {
        setup.calls.fetches.push({ url, options });
        return pendingJson;
      },
    }),
  });

  try {
    const sending = setup.subject.sendMessageWithTyping();
    await Promise.resolve();

    assert.equal(setup.refs.messages.value[0].role, "user");
    assert.equal(setup.refs.messages.value[1].role, "assistant");
    assert.equal(setup.refs.messages.value[1].content, "思考中...");

    resolveJson({
      answer: "完整答案",
      conversation_id: 42,
      sources: [],
    });
    await sending;

    assert.equal(setup.calls.fetches[0].url, "http://api.test/chat");
    assert.equal(setup.calls.fetches[0].options.method, "POST");
  } finally {
    setup.restoreGlobals();
  }
});

test("sendMessageWithTyping marks the assistant placeholder as typing until the answer arrives", async () => {
  let resolveJson;
  const pendingJson = new Promise((resolve) => {
    resolveJson = resolve;
  });
  const setup = createSubject({
    fetchImpl: async () => ({
      ok: true,
      json: async () => pendingJson,
    }),
  });

  try {
    const sending = setup.subject.sendMessageWithTyping();
    await Promise.resolve();

    assert.equal(setup.refs.messages.value[1].isTyping, true);
    assert.equal(setup.refs.messages.value[1].feedbackSent, undefined);

    resolveJson({
      answer: "完整答案",
      conversation_id: 42,
      sources: [],
    });
    await sending;

    assert.equal(setup.refs.messages.value[1].isTyping, false);
  } finally {
    setup.restoreGlobals();
  }
});

test("sendMessageWithTyping replaces thinking text with typewriter answer after response", async () => {
  const setup = createSubject();

  try {
    await setup.subject.sendMessageWithTyping();

    assert.equal(setup.refs.currentConversationId.value, 42);
    assert.deepEqual(setup.calls.storedItems, [["currentConversationId", "42"]]);
    assert.equal(setup.refs.messages.value[1].content, "完整答案");
    assert.deepEqual(setup.refs.messages.value[1].sources, [{ label: "K1" }]);
    assert.equal(setup.calls.conversationsLoaded, 2);
    assert.equal(setup.calls.balanceLoaded, 1);
  } finally {
    setup.restoreGlobals();
  }
});
