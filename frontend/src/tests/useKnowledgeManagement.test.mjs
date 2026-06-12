import test from "node:test";
import assert from "node:assert/strict";

import { useKnowledgeManagement } from "../useKnowledgeManagement.js";

function ref(value) {
  return { value };
}

function createSubject(overrides = {}) {
  const calls = [];
  const refs = {
    ragStatus: ref({ retrieval: { default_top_k: 9, default_min_score: 0.42 } }),
    knowledgeFileInput: ref({ clicked: false, click() { this.clicked = true; } }),
    selectedKnowledgeFile: ref(null),
    knowledgeNotes: ref(""),
    knowledgeDepartment: ref(""),
    knowledgeLoading: ref(false),
    knowledgeError: ref(""),
    knowledgeIndexJob: ref(null),
    knowledgeDocuments: ref([]),
    knowledgeSources: ref([]),
    knowledgeSearchQuery: ref(""),
    knowledgeSearchResults: ref([]),
    knowledgeSearchLoading: ref(false),
    knowledgeSearchError: ref(""),
    ...overrides.refs,
  };
  const loaders = {
    loadKnowledgeSources: async () => calls.push("sources"),
    loadKnowledgeDocuments: async () => calls.push("documents"),
    loadRagStatus: async () => calls.push("status"),
    loadKnowledgeAudits: async () => calls.push("audits"),
    ...overrides.loaders,
  };
  const subject = useKnowledgeManagement({
    API_BASE: "http://api.test",
    responseError: async (response, fallback) => `${fallback}: ${response.status}`,
    refs,
    loaders,
    fetchImpl: overrides.fetchImpl || (async () => ({ ok: true, json: async () => ({}) })),
    FormDataImpl: overrides.FormDataImpl || class FakeFormData {
      append() {}
    },
    setTimeoutImpl: overrides.setTimeoutImpl || ((callback) => callback()),
  });
  return { calls, refs, subject };
}

test("knowledge defaults come from RAG status when available", () => {
  const { subject } = createSubject();

  assert.equal(subject.defaultKnowledgeTopK(), 9);
  assert.equal(subject.defaultKnowledgeMinScore(), 0.42);
});

test("knowledge defaults fall back when RAG status is missing", () => {
  const { subject } = createSubject({
    refs: {
      ragStatus: ref(null),
    },
  });

  assert.equal(subject.defaultKnowledgeTopK(), 5);
  assert.equal(subject.defaultKnowledgeMinScore(), 0.25);
});

test("knowledge file helpers trigger file input and store selected file", () => {
  const file = { name: "policy.pdf" };
  const { refs, subject } = createSubject();

  subject.chooseKnowledgeFile();
  subject.onKnowledgeFileChange({ target: { files: [file] } });

  assert.equal(refs.knowledgeFileInput.value.clicked, true);
  assert.equal(refs.selectedKnowledgeFile.value, file);
});

test("syncEnabledKnowledgeSources returns early when there are no enabled sources", async () => {
  const { refs, subject, calls } = createSubject({
    refs: {
      knowledgeSources: ref([{ id: 1, enabled: false }]),
    },
  });

  await subject.syncEnabledKnowledgeSources();

  assert.equal(refs.knowledgeLoading.value, false);
  assert.deepEqual(calls, []);
});
