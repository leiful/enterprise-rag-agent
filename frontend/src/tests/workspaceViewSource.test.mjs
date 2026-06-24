import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../views/WorkspaceView.vue", import.meta.url), "utf8");

test("WorkspaceView passes citation source filtering helper into ChatView", () => {
  const chatViewStart = source.indexOf("<ChatView");
  const chatViewEnd = source.indexOf("/>", chatViewStart);
  const chatViewBlock = source.slice(chatViewStart, chatViewEnd);

  assert.match(chatViewBlock, /:referenced-sources="b\.referencedSources"/);
});
