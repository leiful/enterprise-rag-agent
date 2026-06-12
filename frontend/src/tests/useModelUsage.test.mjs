import test from "node:test";
import assert from "node:assert/strict";
import { ref } from "vue";

import { useModelUsage } from "../useModelUsage.js";

test("model usage rows prefer explicit model usage over RAG status fallback", () => {
  const usage = useModelUsage({
    modelUsage: ref({
      today: {
        by_model: [{ model: "primary" }],
        totals: { input_tokens_estimate: 10, output_tokens_estimate: 5 },
      },
    }),
    ragStatus: ref({
      model_usage: {
        today: {
          by_model: [{ model: "fallback" }],
          totals: { input_tokens_estimate: 1, output_tokens_estimate: 1 },
        },
      },
    }),
    isAdmin: ref(true),
    dailyTokenWarningThreshold: 100,
  });

  assert.deepEqual(usage.modelUsageRows("today"), [{ model: "primary" }]);
  assert.equal(usage.todayTokenTotal(), 15);
});

test("daily token warning only appears for admins above the threshold", () => {
  const usage = useModelUsage({
    modelUsage: ref({
      today: {
        totals: { input_tokens_estimate: 80, output_tokens_estimate: 30 },
      },
    }),
    ragStatus: ref(null),
    isAdmin: ref(true),
    dailyTokenWarningThreshold: 100,
  });

  assert.equal(usage.shouldShowDailyTokenWarning(), true);
});

test("model usage trend rows fill the current day with hourly buckets", () => {
  const usage = useModelUsage({
    modelUsage: ref({
      today: {
        trend: [],
      },
    }),
    ragStatus: ref(null),
    isAdmin: ref(true),
    dailyTokenWarningThreshold: 100,
  });

  const rows = usage.modelUsageTrendRows("today");

  assert.equal(rows.length, 24);
  assert.equal(rows[0].request_count, 0);
});
