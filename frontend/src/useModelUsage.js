import { ref } from "vue";
import {
  formatScopeLabel,
  formatUsageBucket,
  formatUsageDay,
} from "./formatters";

export function useModelUsage({ modelUsage, ragStatus, isAdmin, dailyTokenWarningThreshold }) {
  const modelUsagePeriod = ref("today");
  const usageTrendTab = ref("model");
  const usageTrendTooltip = ref(null);

  function modelUsageRows(period = "today") {
    return modelUsage.value?.[period]?.by_model || ragStatus.value?.model_usage?.[period]?.by_model || [];
  }

  function modelUsageTotals(period = "today") {
    return modelUsage.value?.[period]?.totals || ragStatus.value?.model_usage?.[period]?.totals || {};
  }

  function modelUsageScopeRows(period = "today") {
    return modelUsage.value?.[period]?.by_scope || ragStatus.value?.model_usage?.[period]?.by_scope || [];
  }

  function modelUsageTotalTokens(row) {
    return Number(row?.input_tokens_estimate || 0) + Number(row?.output_tokens_estimate || 0);
  }

  function todayTokenTotal() {
    return modelUsageTotalTokens(modelUsageTotals("today"));
  }

  function shouldShowDailyTokenWarning() {
    return isAdmin.value && todayTokenTotal() > dailyTokenWarningThreshold;
  }

  function usageTrendHourKey(value) {
    const date = value instanceof Date ? new Date(value) : new Date(value);
    if (Number.isNaN(date.getTime())) {
      return String(value || "");
    }
    date.setMinutes(0, 0, 0);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    const hour = String(date.getHours()).padStart(2, "0");
    return `${year}-${month}-${day}T${hour}:00:00`;
  }

  function usageTrendBucketKey(value, period = modelUsagePeriod.value) {
    if (!value) {
      return "";
    }
    return period === "today" ? usageTrendHourKey(value) : String(value);
  }

  function todayUsageTrendBuckets() {
    const start = new Date();
    start.setHours(0, 0, 0, 0);
    return Array.from({ length: 24 }, (_, hour) => {
      const bucket = new Date(start);
      bucket.setHours(hour);
      return usageTrendHourKey(bucket);
    });
  }

  function usageTrendCurrentHourIndex() {
    return new Date().getHours();
  }

  function isFutureUsageTrendBucket(bucket, period = modelUsagePeriod.value) {
    if (period !== "today") {
      return false;
    }
    const date = new Date(bucket);
    if (Number.isNaN(date.getTime())) {
      return false;
    }
    const currentHour = new Date();
    currentHour.setMinutes(0, 0, 0);
    return date > currentHour;
  }

  function modelUsageTrendRows(period = modelUsagePeriod.value) {
    const rows = modelUsage.value?.[period]?.trend || ragStatus.value?.model_usage?.[period]?.trend || [];
    const grouped = new Map();
    rows.forEach((row) => {
      const key = usageTrendBucketKey(row.bucket || row.created_at, period);
      if (!key) {
        return;
      }
      const existing = grouped.get(key) || {
        bucket: key,
        input_tokens_estimate: 0,
        output_tokens_estimate: 0,
        request_count: 0,
        document_count: 0,
        scopes: {},
        isFuture: isFutureUsageTrendBucket(key, period),
      };
      existing.input_tokens_estimate += Number(row.input_tokens_estimate || 0);
      existing.output_tokens_estimate += Number(row.output_tokens_estimate || 0);
      existing.request_count += Number(row.request_count || 0);
      existing.document_count += Number(row.document_count || 0);
      existing.scopes[row.usage_scope || "other"] =
        (existing.scopes[row.usage_scope || "other"] || 0) + modelUsageTotalTokens(row);
      grouped.set(key, existing);
    });
    if (period === "today") {
      return todayUsageTrendBuckets().map((bucket) => grouped.get(bucket) || {
        bucket,
        input_tokens_estimate: 0,
        output_tokens_estimate: 0,
        request_count: 0,
        document_count: 0,
        scopes: {},
        isFuture: isFutureUsageTrendBucket(bucket, period),
      });
    }
    return Array.from(grouped.values()).slice(-24);
  }

  function modelUsageTrendAxisTicks(period = modelUsagePeriod.value) {
    const rows = modelUsageTrendRows(period);
    const maxTicks = period === "today" ? 12 : 8;
    const rowTicks = rows.map((row, index) => ({
      bucket: row.bucket,
      index,
      active: modelUsageTotalTokens(row) > 0,
    }));
    if (rows.length <= maxTicks) {
      return rowTicks;
    }
    const lastIndex = rows.length - 1;
    const step = Math.ceil(lastIndex / (maxTicks - 1));
    const ticksByIndex = new Map();
    rowTicks
      .filter((tick) => tick.index === 0 || tick.index === lastIndex || tick.index % step === 0)
      .forEach((tick) => ticksByIndex.set(tick.index, tick));
    if (period === "today") {
      rowTicks
        .filter((tick) => tick.active)
        .forEach((tick) => ticksByIndex.set(tick.index, tick));
    }
    const ticks = Array.from(ticksByIndex.values()).sort((a, b) => a.index - b.index);
    if (ticks.at(-1)?.index !== lastIndex) {
      ticks.push({ bucket: rows.at(-1)?.bucket, index: lastIndex, active: false });
    }
    return ticks;
  }

  function modelUsageTrendAxisTickStyle(tick, period = modelUsagePeriod.value) {
    const rows = modelUsageTrendRows(period);
    const width = 300;
    const paddingX = 8;
    const innerWidth = width - paddingX * 2;
    const slotWidth = rows.length <= 1 ? innerWidth : innerWidth / rows.length;
    const barCenter = rows.length <= 1
      ? paddingX + innerWidth / 2
      : paddingX + tick.index * slotWidth + slotWidth / 2;
    const left = (barCenter / width) * 100;
    return {
      left: `${left}%`,
      transform: left < 2 ? "translateX(0)" : left > 98 ? "translateX(-100%)" : "translateX(-50%)",
      textAlign: left < 2 ? "left" : left > 98 ? "right" : "center",
      fontWeight: tick.active ? 700 : 500,
      color: tick.active ? "#172033" : "#64748b",
    };
  }

  function modelUsageTrendSeriesLabel(row, groupBy = usageTrendTab.value) {
    if (groupBy === "scenario") {
      return formatScopeLabel(row?.usage_scope || "other");
    }
    return row?.model || "unknown";
  }

  function modelUsageTrendSeries(period = modelUsagePeriod.value, groupBy = usageTrendTab.value) {
    const rows = modelUsage.value?.[period]?.trend || ragStatus.value?.model_usage?.[period]?.trend || [];
    const buckets = period === "today"
      ? todayUsageTrendBuckets()
      : Array.from(new Set(rows.map((row) => usageTrendBucketKey(row.bucket || row.created_at, period)).filter(Boolean))).sort();
    const seriesMap = new Map();
    rows.forEach((row) => {
      const label = modelUsageTrendSeriesLabel(row, groupBy);
      const bucket = usageTrendBucketKey(row.bucket || row.created_at, period);
      if (!bucket) {
        return;
      }
      const series = seriesMap.get(label) || {
        label,
        provider: row.provider,
        model: row.model,
        operation: row.operation,
        total: 0,
        values: new Map(),
      };
      const tokens = modelUsageTotalTokens(row);
      series.total += tokens;
      series.values.set(bucket, (series.values.get(bucket) || 0) + tokens);
      seriesMap.set(label, series);
    });
    const selectedSeries = Array.from(seriesMap.values())
      .sort((a, b) => b.total - a.total)
      .slice(0, 5);
    return selectedSeries.map((series, seriesIndex) => ({
      ...series,
      color: modelUsageTrendColor(seriesIndex),
      seriesIndex,
      seriesCount: selectedSeries.length,
      points: buckets.map((bucket) => ({
        bucket,
        input_tokens_estimate: series.values.get(bucket) || 0,
        output_tokens_estimate: 0,
        isFuture: isFutureUsageTrendBucket(bucket, period),
      })),
    }));
  }

  function modelUsageTrendColor(index) {
    return ["#2563eb", "#16a34a", "#dc2626", "#9333ea", "#d97706"][index % 5];
  }

  function modelUsageTrendStackedBars(period = modelUsagePeriod.value, groupBy = usageTrendTab.value) {
    const seriesList = modelUsageTrendSeries(period, groupBy);
    const buckets = modelUsageTrendRows(period).map((row) => row.bucket);
    return buckets.map((bucket) => {
      const segments = seriesList
        .map((series) => {
          const point = series.points.find((item) => item.bucket === bucket);
          return {
            bucket,
            label: series.label,
            color: series.color,
            tokens: modelUsageTotalTokens(point),
            isFuture: Boolean(point?.isFuture),
          };
        })
        .filter((segment) => segment.tokens > 0);
      return {
        bucket,
        segments,
        total: segments.reduce((sum, segment) => sum + segment.tokens, 0),
      };
    });
  }

  function modelUsageTrendBarSegments(period = modelUsagePeriod.value, groupBy = usageTrendTab.value) {
    const bars = modelUsageTrendStackedBars(period, groupBy);
    const maxTokens = Math.max(1, ...bars.map((bar) => bar.total));
    const width = 300;
    const height = 120;
    const paddingX = 8;
    const paddingTop = 12;
    const paddingBottom = 8;
    const innerWidth = width - paddingX * 2;
    const innerHeight = height - paddingTop - paddingBottom;
    const slotWidth = bars.length <= 1 ? innerWidth : innerWidth / bars.length;
    const barWidth = Math.max(3, Math.min(18, slotWidth * 0.72));
    const segments = [];

    bars.forEach((bar, index) => {
      if (!bar.total) {
        return;
      }
      const x = bars.length <= 1
        ? paddingX + (innerWidth - barWidth) / 2
        : paddingX + index * slotWidth + (slotWidth - barWidth) / 2;
      let yCursor = height - paddingBottom;
      const barHeight = Math.max(10, Math.sqrt(bar.total / maxTokens) * innerHeight);
      bar.segments.forEach((segment) => {
        const segmentHeight = Math.max(2, (segment.tokens / bar.total) * barHeight);
        yCursor -= segmentHeight;
        segments.push({
          ...segment,
          total: bar.total,
          x: Number(x.toFixed(2)),
          y: Number(Math.max(paddingTop, yCursor).toFixed(2)),
          width: Number(barWidth.toFixed(2)),
          height: Number(Math.min(segmentHeight, height - paddingBottom - paddingTop).toFixed(2)),
        });
      });
    });

    return segments;
  }

  function showUsageTrendTooltip(segment) {
    usageTrendTooltip.value = {
      label: segment.label,
      color: segment.color,
      bucket: segment.bucket,
      tokens: segment.tokens,
      x: `${Math.max(8, Math.min(86, ((segment.x + segment.width / 2) / 300) * 100))}%`,
      y: `${Math.max(8, Math.min(76, (segment.y / 120) * 100))}%`,
    };
  }

  function hideUsageTrendTooltip() {
    usageTrendTooltip.value = null;
  }

  function modelUsageRecentEvents(period = modelUsagePeriod.value) {
    return modelUsage.value?.[period]?.recent_events || ragStatus.value?.model_usage?.[period]?.recent_events || [];
  }

  function formatUsageTrendBucketForPeriod(value, period = modelUsagePeriod.value) {
    return period === "today" ? formatUsageBucket(value) : formatUsageDay(value);
  }

  function formatUsageTrendAxisBucketForPeriod(value, period = modelUsagePeriod.value) {
    if (!value) {
      return "";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return String(value);
    }
    if (period === "today") {
      return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }
    return formatUsageDay(value);
  }

  function setModelUsagePeriod(period) {
    modelUsagePeriod.value = period;
  }

  return {
    modelUsagePeriod,
    usageTrendTab,
    usageTrendTooltip,
    modelUsageRows,
    modelUsageTotals,
    modelUsageScopeRows,
    modelUsageTotalTokens,
    todayTokenTotal,
    shouldShowDailyTokenWarning,
    usageTrendCurrentHourIndex,
    modelUsageTrendRows,
    modelUsageTrendAxisTicks,
    modelUsageTrendAxisTickStyle,
    modelUsageTrendSeries,
    modelUsageTrendBarSegments,
    showUsageTrendTooltip,
    hideUsageTrendTooltip,
    modelUsageRecentEvents,
    formatUsageTrendBucket: formatUsageTrendBucketForPeriod,
    formatUsageTrendAxisBucket: formatUsageTrendAxisBucketForPeriod,
    setModelUsagePeriod,
  };
}
