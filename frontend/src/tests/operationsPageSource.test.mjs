import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../views/OperationsPage.vue", import.meta.url), "utf8");

test("OperationsPage shows answer previews in feedback lists", () => {
  assert.match(source, /class="feedback-answer-preview"/);
  assert.match(source, /:class="\{ expanded: isAnswerExpanded\(item\) \}"/);
});

test("OperationsPage includes show more controls for long answer previews", () => {
  assert.match(source, /Show more/);
  assert.match(source, /Show less/);
  assert.match(source, /shouldShowAnswerToggle\(item\.answer\)/);
  assert.match(source, /toggleAnswer\(item\)/);
});
