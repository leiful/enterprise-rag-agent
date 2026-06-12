import test from "node:test";
import assert from "node:assert/strict";

import { useFeedback } from "../useFeedback.js";

function ref(value) {
  return { value };
}

function createSubject(overrides = {}) {
  const calls = [];
  let requestBody = null;
  const refs = {
    messages: ref([
      { role: "user", content: "What is the policy?" },
      { role: "assistant", content: "Use source K1", sources: [{ label: "K1" }] },
    ]),
    currentConversationId: ref(12),
    isAdmin: ref(true),
    ...overrides.refs,
  };
  const loaders = {
    cacheCurrentConversation: () => calls.push("cache"),
    loadRagFeedback: async () => calls.push("feedback"),
    loadRagStatus: async () => calls.push("status"),
    ...overrides.loaders,
  };
  const subject = useFeedback({
    API_BASE: "http://api.test",
    responseError: async (response, fallback) => `${fallback}: ${response.status}`,
    refs,
    loaders,
    fetchImpl: overrides.fetchImpl || (async (_url, options) => {
      requestBody = JSON.parse(options.body);
      return { ok: true, json: async () => ({ message_id: 99 }) };
    }),
  });
  return {
    calls,
    refs,
    getRequestBody: () => requestBody,
    subject,
  };
}

test("submitFeedback posts the previous user query and marks the message", async () => {
  const { calls, refs, getRequestBody, subject } = createSubject();
  const message = refs.messages.value[1];

  await subject.submitFeedback(message, 1, "useful");

  assert.deepEqual(getRequestBody(), {
    feedback_type: "useful",
    conversation_id: 12,
    message_id: null,
    query: "What is the policy?",
    answer: "Use source K1",
    sources: [{ label: "K1" }],
  });
  assert.equal(message.id, 99);
  assert.equal(message.feedbackSent, "useful");
  assert.equal(message.feedbackLoading, false);
  assert.deepEqual(calls, ["cache", "feedback", "status"]);
});

test("submitFeedback skips messages already sent or loading", async () => {
  const { calls, subject } = createSubject();
  const message = {
    role: "assistant",
    content: "Already handled",
    feedbackSent: "useful",
  };

  await subject.submitFeedback(message, 1, "not_useful");

  assert.deepEqual(calls, []);
});

test("submitFeedback records errors on the message", async () => {
  const { refs, subject } = createSubject({
    fetchImpl: async () => ({ ok: false, status: 500, json: async () => ({}) }),
  });
  const message = refs.messages.value[1];

  await subject.submitFeedback(message, 1, "wrong_source");

  assert.equal(message.feedbackError, "Feedback failed with status 500: 500");
  assert.equal(message.feedbackLoading, false);
});
