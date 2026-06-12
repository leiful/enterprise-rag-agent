export function useFeedback({
  API_BASE,
  responseError,
  refs,
  loaders,
  fetchImpl = fetch,
}) {
  const { messages, currentConversationId, isAdmin } = refs;
  const { cacheCurrentConversation, loadRagFeedback, loadRagStatus } = loaders;

  async function submitFeedback(message, index, feedbackType) {
    if (!message || message.feedbackLoading || message.feedbackSent) {
      return;
    }

    message.feedbackLoading = true;
    message.feedbackError = "";

    try {
      const previousUserMessage = [...messages.value]
        .slice(0, index)
        .reverse()
        .find((item) => item.role === "user");
      const response = await fetchImpl(`${API_BASE}/feedback`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
        body: JSON.stringify({
          feedback_type: feedbackType,
          conversation_id: currentConversationId.value,
          message_id: message.id || null,
          query: previousUserMessage?.content || "",
          answer: message.content || "",
          sources: message.sources || [],
        }),
      });

      if (!response.ok) {
        throw new Error(await responseError(response, `Feedback failed with status ${response.status}`));
      }

      const data = await response.json();
      if (data.message_id) {
        message.id = data.message_id;
      }
      message.feedbackSent = feedbackType;
      cacheCurrentConversation();
      if (isAdmin.value) {
        await loadRagFeedback();
        await loadRagStatus();
      }
    } catch (err) {
      message.feedbackError = err.message || "Feedback failed";
    } finally {
      message.feedbackLoading = false;
    }
  }

  return {
    submitFeedback,
  };
}
