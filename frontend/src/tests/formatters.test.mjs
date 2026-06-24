import test from "node:test";
import assert from "node:assert/strict";

import {
  feedbackTypeLabel,
  formatDepartments,
  formatFileSize,
  formatPercent,
  formatSourceName,
  formatStatusCount,
  referencedSources,
  normalizeMessages,
} from "../formatters.js";

test("formatStatusCount returns zero for missing count keys", () => {
  assert.equal(formatStatusCount({ completed: 3 }, "failed"), 0);
});

test("formatPercent renders numeric ratios as whole percentages", () => {
  assert.equal(formatPercent(0.456), "46%");
});

test("feedbackTypeLabel falls back to the raw type for unknown values", () => {
  assert.equal(feedbackTypeLabel("needs_review"), "needs_review");
});

test("formatDepartments describes empty department lists", () => {
  assert.equal(formatDepartments([]), "No departments");
  assert.equal(formatDepartments(["HR", "", "Finance"]), "HR, Finance");
});

test("formatFileSize uses human readable units", () => {
  assert.equal(formatFileSize(0), "0 B");
  assert.equal(formatFileSize(1536), "1.5 KB");
});

test("formatSourceName extracts uploaded file names from generated ids", () => {
  assert.equal(formatSourceName("source__policy.pdf"), "policy.pdf");
});

test("referencedSources keeps only sources cited in the answer text", () => {
  const message = {
    content: "第一条依据来自 [K1]，补充步骤见 [K4]。",
    sources: [
      { label: "K1", document_id: "manual.pdf" },
      { label: "K2", document_id: "manual.pdf" },
      { label: "K4", document_id: "manual.pdf" },
    ],
  };

  assert.deepEqual(
    referencedSources(message).map((source) => source.label),
    ["K1", "K4"],
  );
});

test("normalizeMessages returns an assistant placeholder for empty histories", () => {
  const [message] = normalizeMessages([]);

  assert.equal(message.role, "assistant");
  assert.ok(message.content.length > 0);
});
