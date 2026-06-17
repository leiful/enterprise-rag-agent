import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../views/OperationsPage.vue", import.meta.url), "utf8");
const styles = readFileSync(new URL("../style.css", import.meta.url), "utf8");

function cssBlock(selector) {
  const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return styles.match(new RegExp(`${escapedSelector}\\s*\\{([^}]*)\\}`))?.[1] || "";
}

function sourceBetween(start, end) {
  const startIndex = source.indexOf(start);
  const endIndex = source.indexOf(end, startIndex);
  return startIndex >= 0 && endIndex >= 0 ? source.slice(startIndex, endIndex) : "";
}

function assertBefore(haystack, earlier, later) {
  const earlierIndex = haystack.indexOf(earlier);
  const laterIndex = haystack.indexOf(later);
  assert.notEqual(earlierIndex, -1, `${earlier} should exist`);
  assert.notEqual(laterIndex, -1, `${later} should exist`);
  assert.ok(earlierIndex < laterIndex, `${earlier} should appear before ${later}`);
}

test("OperationsPage shows answer previews in feedback lists", () => {
  assert.match(source, /class="feedback-answer-preview"/);
  assert.match(source, /:class="\{ expanded: isAnswerExpanded\(item\) \}"/);
});

test("OperationsPage answer previews clip to two lines without ellipsis", () => {
  const answerPreviewStyles = cssBlock(".feedback-answer-preview");

  assert.doesNotMatch(answerPreviewStyles, /-webkit-line-clamp/);
  assert.match(answerPreviewStyles, /max-height:\s*calc\(1\.5em \* 2 \+ 16px\);/);
});

test("OperationsPage does not show a separate Answer feedback refresh button", () => {
  const answerFeedbackHeader = sourceBetween(
    "<h3>Answer feedback</h3>",
    "<p v-if=\"feedbackError\"",
  );

  assert.doesNotMatch(answerFeedbackHeader, /Refresh/);
  assert.doesNotMatch(answerFeedbackHeader, /loadRagFeedback/);
});

test("OperationsPage does not show a selected feedback clear row", () => {
  assert.doesNotMatch(source, /class="feedback-filter-row"/);
  assert.doesNotMatch(source, /Clear/);
});

test("OperationsPage places show more controls in feedback item headers", () => {
  assert.match(source, /Show more/);
  assert.match(source, /Show less/);
  assert.match(source, /shouldShowAnswerToggle\(item\.answer\)/);
  assert.match(source, /toggleAnswer\(item\)/);
  assert.match(source, /class="feedback-question-group"[\s\S]*class="feedback-question"[\s\S]*shouldShowAnswerToggle\(item\.answer\)/);
});

test("OperationsPage keeps feedback questions aligned with inline show more controls", () => {
  const questionOverrideStyles = cssBlock(".feedback-item .feedback-question");

  assert.match(questionOverrideStyles, /margin:\s*0;/);
  assert.match(questionOverrideStyles, /line-height:\s*1\.35;/);
  assert.match(cssBlock(".feedback-inline-button"), /line-height:\s*1\.35;/);
});

test("OperationsPage keeps feedback user and type labels spaced apart", () => {
  assert.match(source, /class="feedback-title-meta"/);
  assert.match(cssBlock(".feedback-title-meta"), /gap:\s*8px;/);
  assert.match(cssBlock(".feedback-title-meta"), /font-size:\s*11px;/);
  assert.match(cssBlock(".feedback-title-actions"), /font-size:\s*11px;/);
});

test("OperationsPage gives feedback questions and answers distinct styles", () => {
  assert.match(source, /class="feedback-question"/);
  assert.match(source, /class="feedback-answer-preview"/);
  assert.match(cssBlock(".feedback-question"), /font-weight:\s*700;/);
  assert.match(cssBlock(".feedback-answer-preview"), /background:\s*#f8fafc;/);
});

test("OperationsPage keeps feedback question metadata and actions in one header row", () => {
  const answerFeedbackCard = sourceBetween(
    '<article v-for="item in pagedRagFeedback"',
    '<div v-if="filteredRagFeedback.length > pageSize"',
  );
  const missingDocCard = sourceBetween(
    '<article v-for="item in pagedMissingDocFeedback"',
    '<div v-if="missingDocFeedback.length > pageSize"',
  );

  assert.match(answerFeedbackCard, /class="feedback-item-header"[\s\S]*class="feedback-question-group"[\s\S]*class="feedback-title-meta"[\s\S]*class="feedback-title-actions"/);
  assert.match(missingDocCard, /class="feedback-item-header"[\s\S]*class="feedback-question-group"[\s\S]*class="feedback-title-meta"[\s\S]*class="feedback-title-actions"/);
  assert.match(cssBlock(".feedback-item-header"), /display:\s*flex;/);
  assert.match(cssBlock(".feedback-item-header"), /gap:\s*12px;/);
});

test("OperationsPage omits compact source metadata rows from feedback cards", () => {
  assert.doesNotMatch(source, /<p class="audit-meta">[\s\S]*item\.sources\?\.length \|\| 0[\s\S]*<\/p>/);
});

test("OperationsPage reveals feedback source snippets with expanded answers", () => {
  assert.match(source, /class="feedback-source-list"/);
  assert.match(source, /isAnswerExpanded\(item\) && item\.sources\?\.length/);
  assert.match(source, /\[\{\{ source\.label \}\}\]/);
  assert.match(source, /formatSourceName\(source\.document_id\)/);
  assert.match(source, /source\.text \|\| "No snippet text recorded\."/);
});

test("OperationsPage feedback source metadata matches chat chunk page score format", () => {
  assert.match(source, /formatPageRange: \{ type: Function, required: true \}/);
  assert.match(source, /formatScore: \{ type: Function, required: true \}/);
  assert.match(source, /\| \{\{ formatPageRange\(source\) \}\}/);
  assert.match(source, /\| score \{\{ formatScore\(source\.score\) \}\}/);
});

test("feedback source summaries keep label document and meta in separate grid areas", () => {
  assert.match(cssBlock(".feedback-source-item summary"), /grid-template-areas:\s*"label document meta";/);
});
