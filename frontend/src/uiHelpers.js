import { EMPTY_MESSAGE } from "./appConfig";

export async function responseError(response, fallback) {
  try {
    const data = await response.json();
    return data.detail || fallback;
  } catch {
    return fallback;
  }
}

export function resolveUserRole(data) {
  if (data.role) {
    return data.role;
  }
  return data.username === "admin" ? "admin" : "";
}

export function formatDeepseekBalance(balanceData, isLoading = false) {
  const balances = balanceData?.balance_infos || [];
  if (balances.length === 0) {
    return isLoading ? "Balance..." : "Balance unavailable";
  }

  return balances
    .map((balance) => `${balance.currency === "CNY" ? "DS" : balance.currency} ${balance.total_balance}`)
    .join(" / ");
}

export function ragStatusClass(status) {
  return {
    ok: status === "ok",
    degraded: status === "degraded",
    error: status === "error",
  };
}

export function feedbackOptions(message) {
  if (message.feedbackSent) {
    return [];
  }
  return message.sources?.length
    ? ["useful", "not_useful", "wrong_source", "outdated", "missing_doc"]
    : ["useful", "not_useful", "missing_doc"];
}

export function cloneMessages(rawMessages) {
  return rawMessages.map((message) => ({
    id: message.id,
    role: message.role,
    content: message.content,
    sources: Array.isArray(message.sources) ? [...message.sources] : message.sources,
    created_at: message.created_at,
    feedbackSent: message.feedbackSent,
    feedbackError: message.feedbackError,
  }));
}

export function formatDate(value) {
  if (!value) {
    return "";
  }

  return new Date(value).toLocaleString();
}

export function emptyMessages() {
  return [EMPTY_MESSAGE];
}
