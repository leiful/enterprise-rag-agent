import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("ChatView uses readable Chinese for the empty source message", async () => {
  const source = await readFile(
    new URL("../components/ChatView.vue", import.meta.url),
    "utf8",
  );

  assert.match(source, /本回答未使用知识库来源。/);
  assert.doesNotMatch(source, /鏈.*鐭ヨ瘑搴/);
});
