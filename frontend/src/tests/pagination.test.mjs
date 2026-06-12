import test from "node:test";
import assert from "node:assert/strict";

import { paginateItems, totalPages } from "../pagination.js";

test("totalPages keeps at least one page for empty totals", () => {
  assert.equal(totalPages(0, 8), 1);
  assert.equal(totalPages(undefined, 8), 1);
});

test("totalPages rounds partial pages up", () => {
  assert.equal(totalPages(17, 8), 3);
});

test("paginateItems clamps page numbers below one", () => {
  assert.deepEqual(paginateItems(["a", "b", "c"], 0, 2), ["a", "b"]);
});

test("paginateItems returns the requested page slice", () => {
  assert.deepEqual(paginateItems(["a", "b", "c", "d"], 2, 2), ["c", "d"]);
});
