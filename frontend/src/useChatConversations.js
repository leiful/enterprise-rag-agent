import { nextTick } from "vue";

export function useChatConversations({
  API_BASE,
  refs,
  loaders,
  helpers,
  typing = {},
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
  const typingDelayMs = typing.delayMs ?? 12;
  const typingChunkSize = typing.chunkSize ?? 3;
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

  function wait(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function revealAnswer(message, answer) {
    message.content = "";
    if (!answer) {
      return;
    }

    for (let index = 0; index < answer.length; index += typingChunkSize) {
      message.content += answer.slice(index, index + typingChunkSize);
      await scrollMessagesToBottom();
      if (typingDelayMs > 0 && index + typingChunkSize < answer.length) {
        await wait(typingDelayMs);
      }
    }
  }

  async function sendMessageWithTyping() {
    const text = input.value.trim();

    if (!text || loading.value) {
      return;
    }

    messages.value.push({ role: "user", content: text, created_at: new Date().toISOString() });
    const assistantIndex = messages.value.length;
    messages.value.push({
      role: "assistant",
      content: "思考中...",
      sources: [],
      created_at: new Date().toISOString(),
      isTyping: true,
    });
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
          throw new Error("Chat API is unavailable. Restart the backend service and try again.");
        }
        throw new Error(`Request failed with status ${response.status}`);
      }

      const data = await response.json();
      currentConversationId.value = data.conversation_id;
      if (data.conversation_id) {
        localStorage.setItem("currentConversationId", String(data.conversation_id));
        await loadConversations();
      }

      messages.value[assistantIndex].isTyping = false;
      messages.value[assistantIndex].sources = data.sources || [];
      await revealAnswer(messages.value[assistantIndex], data.answer || "");

      cacheCurrentConversation();
      await loadConversations();
      await loadDeepseekBalance();
    } catch (err) {
      const message = err.message || "Request failed";
      messages.value[assistantIndex].isTyping = false;
      messages.value[assistantIndex].content = message === "Failed to fetch"
        ? "请求失败，请稍后重试。"
        : message;
      error.value = messages.value[assistantIndex].content;
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
    sendMessageWithTyping,
    clearConversationState,
  };
}
