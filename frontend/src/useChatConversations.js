import { nextTick } from "vue";

export function useChatConversations({
  API_BASE,
  refs,
  loaders,
  helpers,
}) {
  const {
    input,
    activeView,
    loading,
    conversationLoading,
    error,
    chatView,
    conversations,
    currentConversationId,
    messages,
    deepseekBalance,
    balanceError,
    balanceLoading,
  } = refs;
  const { loadConversations, loadDeepseekBalance } = loaders;
  const { cloneMessages, emptyMessages, normalizeMessages, decodeSourcesHeader } = helpers;
  const conversationMessagesCache = new Map();
  let conversationLoadToken = 0;

  function cacheCurrentConversation() {
    if (!currentConversationId.value) {
      return;
    }

    conversationMessagesCache.set(currentConversationId.value, cloneMessages(messages.value));
  }

  async function restoreConversation() {
    const savedId = Number(localStorage.getItem("currentConversationId"));
    if (!savedId || !conversations.value.some((conversation) => conversation.id === savedId)) {
      newConversation();
      return;
    }

    await selectConversation(savedId);
  }

  function newConversation() {
    currentConversationId.value = null;
    localStorage.removeItem("currentConversationId");
    messages.value = emptyMessages();
  }

  function openNewChat() {
    activeView.value = "chat";
    newConversation();
  }

  async function scrollMessagesToBottom() {
    await nextTick();
    chatView.value?.scrollToBottom();
  }

  async function selectConversation(conversationId) {
    error.value = "";
    const selectedId = Number(conversationId);

    if (currentConversationId.value === selectedId && messages.value.length > 0) {
      await scrollMessagesToBottom();
      return;
    }

    if (conversationMessagesCache.has(selectedId)) {
      currentConversationId.value = selectedId;
      localStorage.setItem("currentConversationId", String(selectedId));
      messages.value = cloneMessages(conversationMessagesCache.get(selectedId));
      await scrollMessagesToBottom();
      return;
    }

    currentConversationId.value = selectedId;
    localStorage.setItem("currentConversationId", String(selectedId));
    messages.value = [];
    conversationLoading.value = true;
    const loadToken = conversationLoadToken + 1;
    conversationLoadToken = loadToken;
    await scrollMessagesToBottom();

    try {
      const response = await fetch(`${API_BASE}/conversations/${selectedId}/messages`, {
        credentials: "include",
      });

      if (!response.ok) {
        throw new Error(`Failed to load messages with status ${response.status}`);
      }

      const data = await response.json();
      if (loadToken !== conversationLoadToken) {
        return;
      }

      messages.value = normalizeMessages(data.messages);
      conversationMessagesCache.set(selectedId, cloneMessages(messages.value));

      await scrollMessagesToBottom();
    } catch (err) {
      if (loadToken === conversationLoadToken) {
        error.value = err.message || "Failed to load conversation";
      }
    } finally {
      if (loadToken === conversationLoadToken) {
        conversationLoading.value = false;
      }
    }
  }

  async function openConversation(conversationId) {
    activeView.value = "chat";
    await selectConversation(conversationId);
  }

  async function sendMessage() {
    const text = input.value.trim();

    if (!text || loading.value) {
      return;
    }

    messages.value.push({ role: "user", content: text, created_at: new Date().toISOString() });
    input.value = "";
    error.value = "";
    loading.value = true;
    await scrollMessagesToBottom();

    try {
      const response = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
        body: JSON.stringify({
          message: text,
          conversation_id: currentConversationId.value,
        }),
      });

      if (!response.ok) {
        if (response.status === 404) {
          throw new Error("Chat job API is unavailable. Restart the backend service and try again.");
        }
        throw new Error(`Request failed with status ${response.status}`);
      }

      const data = await response.json();
      currentConversationId.value = data.conversation_id;
      localStorage.setItem("currentConversationId", String(data.conversation_id));
      messages.value.push({
        role: "assistant",
        content: data.answer || "",
        sources: data.sources || [],
        created_at: new Date().toISOString(),
      });
      await scrollMessagesToBottom();
      await loadConversations();
      cacheCurrentConversation();
    } catch (err) {
      error.value = err.message || "Request failed";
    } finally {
      loading.value = false;
    }
  }

  async function sendMessageStream() {
    const text = input.value.trim();

    if (!text || loading.value) {
      return;
    }

    messages.value.push({ role: "user", content: text, created_at: new Date().toISOString() });
    const assistantIndex = messages.value.length;
    messages.value.push({ role: "assistant", content: "", sources: [], created_at: new Date().toISOString() });
    input.value = "";
    error.value = "";
    loading.value = true;
    await scrollMessagesToBottom();

    try {
      const response = await fetch(`${API_BASE}/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
        body: JSON.stringify({
          message: text,
          conversation_id: currentConversationId.value,
        }),
      });

      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
      }

      const conversationId = Number(response.headers.get("X-Conversation-Id"));
      if (conversationId) {
        currentConversationId.value = conversationId;
        localStorage.setItem("currentConversationId", String(conversationId));
        await loadConversations();
      }

      messages.value[assistantIndex].sources = decodeSourcesHeader(
        response.headers.get("X-Knowledge-Sources"),
      );

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("Streaming response is not available.");
      }

      const decoder = new TextDecoder();
      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          break;
        }

        messages.value[assistantIndex].content += decoder.decode(value, { stream: true });
        await scrollMessagesToBottom();
      }

      const tail = decoder.decode();
      if (tail) {
        messages.value[assistantIndex].content += tail;
        await scrollMessagesToBottom();
      }

      cacheCurrentConversation();
      await loadConversations();
      await loadDeepseekBalance();
    } catch (err) {
      messages.value[assistantIndex].content ||= err.message || "Request failed";
      error.value = err.message || "Request failed";
    } finally {
      loading.value = false;
    }
  }

  function clearConversationState() {
    currentConversationId.value = null;
    conversations.value = [];
    messages.value = emptyMessages();
    conversationMessagesCache.clear();
    localStorage.removeItem("currentConversationId");
    deepseekBalance.value = null;
    balanceError.value = "";
    balanceLoading.value = false;
  }

  return {
    conversationMessagesCache,
    cacheCurrentConversation,
    restoreConversation,
    newConversation,
    openNewChat,
    scrollMessagesToBottom,
    selectConversation,
    openConversation,
    sendMessage,
    sendMessageStream,
    clearConversationState,
  };
}
