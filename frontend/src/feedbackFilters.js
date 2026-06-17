export const FEEDBACK_FILTERS = [
  { type: "", label: "Total" },
  { type: "useful", label: "Useful" },
  { type: "not_useful", label: "Not useful" },
  { type: "wrong_source", label: "Wrong source" },
  { type: "outdated", label: "Outdated" },
  { type: "missing_doc", label: "Missing doc" },
];

export function feedbackFilterOptions(summary) {
  return FEEDBACK_FILTERS.map((filter) => ({
    ...filter,
    count: filter.type
      ? Number(summary?.by_type?.[filter.type] || 0)
      : Number(summary?.total || 0),
  }));
}

export function filterFeedbackByType(feedback, type) {
  if (!type) {
    return feedback;
  }
  return feedback.filter((item) => item.feedback_type === type);
}
