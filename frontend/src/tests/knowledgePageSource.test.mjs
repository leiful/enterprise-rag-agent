import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

test("knowledge upload department options match managed departments only", () => {
  const source = readFileSync(new URL("../views/KnowledgePage.vue", import.meta.url), "utf8");

  assert.equal(source.includes('<option value="">Public</option>'), false);
  assert.equal(source.includes("Select department"), true);
});
