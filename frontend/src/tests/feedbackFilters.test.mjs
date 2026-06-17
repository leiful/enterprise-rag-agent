import test from "node:test";
import assert from "node:assert/strict";

import {
  feedbackFilterOptions,
  filterFeedbackByType,
} from "../feedbackFilters.js";

test("feedbackFilterOptions mirrors the chat feedback choices", () => {
  const options = feedbackFilterOptions({
    total: 15,
    by_type: {
      useful: 4,
      not_useful: 3,
      wrong_source: 2,
      outdated: 1,
      missing_doc: 5,
    },
  });

  assert.deepEqual(options, [
    { type: "", label: "Total", count: 15 },
    { type: "useful", label: "Useful", count: 4 },
    { type: "not_useful", label: "Not useful", count: 3 },
    { type: "wrong_source", label: "Wrong source", count: 2 },
    { type: "outdated", label: "Outdated", count: 1 },
    { type: "missing_doc", label: "Missing doc", count: 5 },
  ]);
});

test("filterFeedbackByType returns all feedback until a type is selected", () => {
  const feedback = [
    { id: 1, feedback_type: "useful" },
    { id: 2, feedback_type: "wrong_source" },
  ];

  assert.equal(filterFeedbackByType(feedback, null), feedback);
});

test("filterFeedbackByType keeps only the selected feedback type", () => {
  const feedback = [
    { id: 1, feedback_type: "useful" },
    { id: 2, feedback_type: "wrong_source" },
    { id: 3, feedback_type: "wrong_source" },
  ];

  assert.deepEqual(filterFeedbackByType(feedback, "wrong_source"), [
    { id: 2, feedback_type: "wrong_source" },
    { id: 3, feedback_type: "wrong_source" },
  ]);
});
