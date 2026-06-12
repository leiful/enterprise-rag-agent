<script setup>
defineProps({
  modelUsagePeriod: { type: String, required: true },
  modelUsageError: { type: String, default: "" },
  usageTrendTab: { type: String, required: true },
  usageTrendTooltip: { type: Object, default: null },
  pageSize: { type: Number, required: true },
  usageEventsPage: { type: Number, required: true },
  usageEventsTotalPages: { type: Number, required: true },
  pagedModelUsageEvents: { type: Array, required: true },
  setModelUsagePeriod: { type: Function, required: true },
  setUsageTrendTab: { type: Function, required: true },
  modelUsageTrendRows: { type: Function, required: true },
  modelUsageTrendBarSegments: { type: Function, required: true },
  showUsageTrendTooltip: { type: Function, required: true },
  hideUsageTrendTooltip: { type: Function, required: true },
  formatNumber: { type: Function, required: true },
  formatUsageTrendBucket: { type: Function, required: true },
  modelUsageTrendAxisTicks: { type: Function, required: true },
  modelUsageTrendAxisTickStyle: { type: Function, required: true },
  formatUsageTrendAxisBucket: { type: Function, required: true },
  modelUsageTrendSeries: { type: Function, required: true },
  modelUsageRecentEvents: { type: Function, required: true },
  formatUsageBucket: { type: Function, required: true },
  formatOperationLabel: { type: Function, required: true },
  formatScopeLabel: { type: Function, required: true },
  modelUsageTotalTokens: { type: Function, required: true },
  formatUsageEventDetail: { type: Function, required: true },
  setUsageEventsPage: { type: Function, required: true },
});
</script>

<template>
  <div class="users-column">
          <section class="users-section">
            <div class="section-header">
              <div>
                <h2>Token Monitor</h2>
                <p>Track model usage across chat, tests, knowledge search, and indexing.</p>
              </div>
              <div class="header-actions">
                <select
                  :value="modelUsagePeriod"
                  class="period-select"
                  @change="setModelUsagePeriod($event.target.value)"
                >
                  <option value="today">Today</option>
                  <option value="last_7_days">Last 7 days</option>
                  <option value="last_30_days">Last 30 days</option>
                </select>
              </div>
            </div>

            <p v-if="modelUsageError" class="error users-error">{{ modelUsageError }}</p>

            <div class="usage-dashboard">
              <div class="usage-section">
                <div class="operations-tabs" role="tablist" aria-label="Token trend grouping">
                  <button
                    type="button"
                    :class="{ active: usageTrendTab === 'model' }"
                    @click="setUsageTrendTab('model')"
                  >
                    By model
                  </button>
                  <button
                    type="button"
                    :class="{ active: usageTrendTab === 'scenario' }"
                    @click="setUsageTrendTab('scenario')"
                  >
                    By scenario
                  </button>
                </div>
                <div v-if="modelUsageTrendRows(modelUsagePeriod).length" class="usage-bar-chart">
                  <div class="usage-chart-plot">
                    <svg viewBox="0 0 300 120" preserveAspectRatio="none" role="img" aria-label="Token usage trend">
                    <rect
                      v-for="segment in modelUsageTrendBarSegments(modelUsagePeriod, usageTrendTab)"
                      :key="`${segment.bucket}-${segment.label}`"
                      class="usage-bar-segment"
                      :x="segment.x"
                      :y="segment.y"
                      :width="segment.width"
                      :height="segment.height"
                      :style="{ fill: segment.color }"
                      tabindex="0"
                      @mouseenter="showUsageTrendTooltip(segment)"
                      @mouseleave="hideUsageTrendTooltip"
                      @focus="showUsageTrendTooltip(segment)"
                      @blur="hideUsageTrendTooltip"
                    />
                    </svg>
                    <div
                      v-if="usageTrendTooltip"
                      class="usage-chart-tooltip"
                      :style="{ left: usageTrendTooltip.x, top: usageTrendTooltip.y }"
                    >
                      <strong>{{ formatNumber(usageTrendTooltip.tokens) }}</strong>
                      <span>{{ usageTrendTooltip.label }} / {{ formatUsageTrendBucket(usageTrendTooltip.bucket) }}</span>
                    </div>
                  </div>
                  <div class="usage-chart-axis">
                    <span
                      v-for="tick in modelUsageTrendAxisTicks(modelUsagePeriod)"
                      :key="tick.bucket"
                      :style="modelUsageTrendAxisTickStyle(tick, modelUsagePeriod)"
                    >
                      {{ formatUsageTrendAxisBucket(tick.bucket, modelUsagePeriod) }}
                    </span>
                  </div>
                  <div class="usage-chart-legend">
                    <span
                      v-for="series in modelUsageTrendSeries(modelUsagePeriod, usageTrendTab)"
                      :key="`${series.label}-legend`"
                    >
                      <i :style="{ background: series.color }"></i>
                      {{ series.label }}: {{ formatNumber(series.total) }}
                    </span>
                  </div>
                </div>
                <p v-else class="empty-state">No trend data for this period.</p>
              </div>

              <div class="usage-section">
                <div class="users-subsection-header">
                  <h3>Recent calls</h3>
                </div>
                <template v-if="modelUsageRecentEvents(modelUsagePeriod).length">
                  <div class="usage-table usage-events-table">
                    <div class="usage-table-row usage-event-row usage-table-head">
                      <span>Time</span>
                      <span>Model</span>
                      <span>Use</span>
                      <span>Scenario</span>
                      <span>Tokens</span>
                      <span>Input</span>
                      <span>Output</span>
                      <span>Chunks/docs</span>
                      <span>Detail</span>
                    </div>
                    <div
                      v-for="row in pagedModelUsageEvents"
                      :key="row.id"
                      class="usage-table-row usage-event-row"
                    >
                      <span>{{ formatUsageBucket(row.created_at) }}</span>
                      <span>{{ row.model }}</span>
                      <span>{{ formatOperationLabel(row.operation) }}</span>
                      <span>{{ formatScopeLabel(row.usage_scope) }}</span>
                      <span>{{ formatNumber(modelUsageTotalTokens(row)) }}</span>
                      <span>{{ formatNumber(row.input_tokens_estimate) }}</span>
                      <span>{{ formatNumber(row.output_tokens_estimate) }}</span>
                      <span>{{ formatNumber(row.document_count) }}</span>
                      <span>{{ formatUsageEventDetail(row) || "-" }}</span>
                    </div>
                  </div>
                  <div v-if="modelUsageRecentEvents(modelUsagePeriod).length > pageSize" class="pagination">
                    <button
                      class="secondary-button"
                      type="button"
                      :disabled="usageEventsPage <= 1"
                      @click="setUsageEventsPage(usageEventsPage - 1)"
                    >
                      Previous
                    </button>
                    <span>Page {{ usageEventsPage }} / {{ usageEventsTotalPages }}</span>
                    <button
                      class="secondary-button"
                      type="button"
                      :disabled="usageEventsPage >= usageEventsTotalPages"
                      @click="setUsageEventsPage(usageEventsPage + 1)"
                    >
                      Next
                    </button>
                  </div>
                </template>
                <p v-else class="empty-state">No recent model calls for this period.</p>
              </div>
            </div>
          </section>
        </div>

</template>
