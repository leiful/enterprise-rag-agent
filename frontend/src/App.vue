<script setup>
import { nextTick, ref } from "vue";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
const input = ref("");
const username = ref("");
const password = ref("");
const currentUser = ref("");
const conversations = ref([]);
const currentConversationId = ref(null);
const activeView = ref("chat");
const loading = ref(false);
const authLoading = ref(false);
const knowledgeLoading = ref(false);
const error = ref("");
const knowledgeError = ref("");
const knowledgeFileInput = ref(null);
const messagesContainer = ref(null);
const selectedKnowledgeFile = ref(null);
const knowledgeNotes = ref("");
const knowledgeDocuments = ref([]);
const knowledgeSearchQuery = ref("");
const knowledgeSearchResults = ref([]);
const knowledgeSearchLoading = ref(false);
const knowledgeSearchError = ref("");
const deepseekBalance = ref(null);
const balanceLoading = ref(false);
const balanceError = ref("");
const emptyMessage = {
  role: "assistant",
  content: "Ready. Ask me to inspect project files, explain code, or run safe checks.",
};
const messages = ref([
  emptyMessage,
]);

const isAuthenticated = ref(false);

async function responseError(response, fallback) {
  try {
    const data = await response.json();
    return data.detail || fallback;
  } catch {
    return fallback;
  }
}

async function checkSession() {
  authLoading.value = true;
  error.value = "";

  try {
    const response = await fetch(`${API_BASE}/me`, {
      credentials: "include",
    });
    const data = await response.json();
    isAuthenticated.value = Boolean(data.authenticated);
    currentUser.value = data.username || "";
    if (isAuthenticated.value) {
      await loadConversations();
      await loadKnowledgeDocuments();
      await loadDeepseekBalance();
      await restoreConversation();
    }
  } catch (err) {
    error.value = err.message || "Session check failed";
  } finally {
    authLoading.value = false;
  }
}

async function login() {
  if (!username.value.trim() || !password.value || authLoading.value) {
    return;
  }

  authLoading.value = true;
  error.value = "";

  try {
    const response = await fetch(`${API_BASE}/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include",
      body: JSON.stringify({
        username: username.value.trim(),
        password: password.value,
      }),
    });

    if (!response.ok) {
      throw new Error(`Login failed with status ${response.status}`);
    }

    const data = await response.json();
    isAuthenticated.value = Boolean(data.authenticated);
    currentUser.value = data.username || username.value.trim();
    password.value = "";
    await loadConversations();
    await loadKnowledgeDocuments();
    await loadDeepseekBalance();
    await restoreConversation();
  } catch (err) {
    error.value = err.message || "Login failed";
  } finally {
    authLoading.value = false;
  }
}

async function logout() {
  authLoading.value = true;
  error.value = "";

  try {
    await fetch(`${API_BASE}/logout`, {
      method: "POST",
      credentials: "include",
    });
  } finally {
    isAuthenticated.value = false;
    currentUser.value = "";
    currentConversationId.value = null;
    conversations.value = [];
    knowledgeDocuments.value = [];
    deepseekBalance.value = null;
    balanceError.value = "";
    messages.value = [emptyMessage];
    localStorage.removeItem("currentConversationId");
    password.value = "";
    authLoading.value = false;
  }
}

async function loadConversations() {
  const response = await fetch(`${API_BASE}/conversations`, {
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(`Failed to load conversations with status ${response.status}`);
  }

  const data = await response.json();
  conversations.value = data.conversations || [];
}

async function loadKnowledgeDocuments() {
  const response = await fetch(`${API_BASE}/knowledge/documents`, {
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(`Failed to load knowledge documents with status ${response.status}`);
  }

  const data = await response.json();
  knowledgeDocuments.value = data.documents || [];
}

async function loadDeepseekBalance() {
  if (balanceLoading.value) {
    return;
  }

  balanceLoading.value = true;
  balanceError.value = "";

  try {
    const response = await fetch(`${API_BASE}/billing/deepseek-balance`, {
      credentials: "include",
    });

    if (!response.ok) {
      throw new Error(`Balance request failed with status ${response.status}`);
    }

    deepseekBalance.value = await response.json();
  } catch (err) {
    balanceError.value = err.message || "Balance unavailable";
    deepseekBalance.value = null;
  } finally {
    balanceLoading.value = false;
  }
}

function formatDeepseekBalance() {
  const balances = deepseekBalance.value?.balance_infos || [];
  if (balances.length === 0) {
    return balanceLoading.value ? "Balance..." : "Balance unavailable";
  }

  return balances
    .map((balance) => `${balance.currency} ${balance.total_balance}`)
    .join(" / ");
}

function chooseKnowledgeFile() {
  knowledgeFileInput.value?.click();
}

function onKnowledgeFileChange(event) {
  selectedKnowledgeFile.value = event.target.files?.[0] || null;
}

async function uploadKnowledgeFile() {
  const file = selectedKnowledgeFile.value;

  if (!file || knowledgeLoading.value) {
    return;
  }

  if (file.size > 50 * 1024 * 1024) {
    knowledgeError.value = "File is larger than 50MB.";
    return;
  }

  knowledgeLoading.value = true;
  knowledgeError.value = "";

  try {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("notes", knowledgeNotes.value.trim());

    const response = await fetch(`${API_BASE}/knowledge/upload`, {
      method: "POST",
      credentials: "include",
      body: formData,
    });

    if (!response.ok) {
      throw new Error(
        await responseError(response, `Upload failed with status ${response.status}`),
      );
    }

    selectedKnowledgeFile.value = null;
    knowledgeNotes.value = "";
    if (knowledgeFileInput.value) {
      knowledgeFileInput.value.value = "";
    }
    await loadKnowledgeDocuments();
  } catch (err) {
    knowledgeError.value = err.message || "Upload failed";
  } finally {
    knowledgeLoading.value = false;
  }
}

async function deleteKnowledgeDocument(documentId) {
  if (knowledgeLoading.value) {
    return;
  }

  knowledgeLoading.value = true;
  knowledgeError.value = "";

  try {
    const response = await fetch(
      `${API_BASE}/knowledge/documents/${encodeURIComponent(documentId)}`,
      {
        method: "DELETE",
        credentials: "include",
      },
    );

    if (!response.ok) {
      throw new Error(`Delete failed with status ${response.status}`);
    }

    await loadKnowledgeDocuments();
  } catch (err) {
    knowledgeError.value = err.message || "Delete failed";
  } finally {
    knowledgeLoading.value = false;
  }
}

async function searchKnowledge() {
  const query = knowledgeSearchQuery.value.trim();

  if (!query || knowledgeSearchLoading.value) {
    return;
  }

  knowledgeSearchLoading.value = true;
  knowledgeSearchError.value = "";

  try {
    const response = await fetch(`${API_BASE}/knowledge/search`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include",
      body: JSON.stringify({
        query,
        top_k: 3,
        min_score: 0.3,
      }),
    });

    if (!response.ok) {
      throw new Error(
        await responseError(response, `Search failed with status ${response.status}`),
      );
    }

    const data = await response.json();
    knowledgeSearchResults.value = data.results || [];
  } catch (err) {
    knowledgeSearchError.value = err.message || "Search failed";
    knowledgeSearchResults.value = [];
  } finally {
    knowledgeSearchLoading.value = false;
  }
}

function formatScore(score) {
  return Number(score || 0).toFixed(3);
}

function decodeSourcesHeader(value) {
  if (!value) {
    return [];
  }

  try {
    const bytes = Uint8Array.from(atob(value), (char) => char.charCodeAt(0));
    const decoded = new TextDecoder().decode(bytes);
    return JSON.parse(decoded);
  } catch {
    return [];
  }
}

function hasSources(message) {
  return Array.isArray(message.sources);
}

function formatDate(value) {
  if (!value) {
    return "";
  }

  return new Date(value).toLocaleString();
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
  messages.value = [emptyMessage];
}

async function scrollMessagesToBottom() {
  await nextTick();

  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
  }
}

async function selectConversation(conversationId) {
  error.value = "";

  try {
    const response = await fetch(`${API_BASE}/conversations/${conversationId}/messages`, {
      credentials: "include",
    });

    if (!response.ok) {
      throw new Error(`Failed to load messages with status ${response.status}`);
    }

    const data = await response.json();
    currentConversationId.value = conversationId;
    localStorage.setItem("currentConversationId", String(conversationId));
    messages.value = (data.messages || []).map((message) => ({
      role: message.role,
      content: message.content,
      sources: message.sources,
    }));

    if (messages.value.length === 0) {
      messages.value = [emptyMessage];
    }

    await scrollMessagesToBottom();
  } catch (err) {
    error.value = err.message || "Failed to load conversation";
  }
}

async function sendMessage() {
  const text = input.value.trim();

  if (!text || loading.value) {
    return;
  }

  messages.value.push({ role: "user", content: text });
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
      throw new Error(`Request failed with status ${response.status}`);
    }

    const data = await response.json();
    currentConversationId.value = data.conversation_id;
    localStorage.setItem("currentConversationId", String(data.conversation_id));
    messages.value.push({
      role: "assistant",
      content: data.answer || "",
      sources: data.sources || [],
    });
    await scrollMessagesToBottom();
    await loadConversations();
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

  messages.value.push({ role: "user", content: text });
  const assistantIndex = messages.value.length;
  messages.value.push({ role: "assistant", content: "", sources: [] });
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

    await loadConversations();
    await loadDeepseekBalance();
  } catch (err) {
    messages.value[assistantIndex].content ||= err.message || "Request failed";
    error.value = err.message || "Request failed";
  } finally {
    loading.value = false;
  }
}

checkSession();
</script>

<template>
  <main class="app-shell">
    <section class="chat-panel">
      <header class="toolbar">
        <div>
          <h1>Agent Console</h1>
          <p>{{ isAuthenticated ? "Private workspace" : "Sign in to continue" }}</p>
        </div>
        <div class="session">
          <span
            v-if="isAuthenticated"
            class="balance-status"
            :class="{ unavailable: balanceError || deepseekBalance?.is_available === false }"
          >
            DeepSeek {{ formatDeepseekBalance() }}
          </span>
          <span class="status">{{ isAuthenticated ? currentUser : "Signed out" }}</span>
          <button
            v-if="isAuthenticated"
            class="secondary-button"
            type="button"
            :disabled="authLoading"
            @click="logout"
          >
            Logout
          </button>
        </div>
      </header>

      <div v-if="!isAuthenticated" class="login-view">
        <div class="login-copy">
          <p class="eyebrow">Secure access</p>
          <h2>Open your agent workspace</h2>
          <p>Use your server account to continue.</p>
        </div>

        <form class="login-form" @submit.prevent="login">
          <label>
            <span>Username</span>
            <input v-model="username" autocomplete="username" placeholder="admin" />
          </label>
          <label>
            <span>Password</span>
            <input
              v-model="password"
              type="password"
              autocomplete="current-password"
              placeholder="Enter password"
            />
          </label>
          <button type="submit" :disabled="authLoading || !username.trim() || !password">
            {{ authLoading ? "Signing in" : "Sign in" }}
          </button>
        </form>
      </div>

      <div v-else class="workspace">
        <aside class="sidebar">
          <div class="view-tabs">
            <button
              class="view-tab"
              :class="{ active: activeView === 'chat' }"
              type="button"
              @click="activeView = 'chat'"
            >
              Chat
            </button>
            <button
              class="view-tab"
              :class="{ active: activeView === 'knowledge' }"
              type="button"
              @click="activeView = 'knowledge'"
            >
              Knowledge
            </button>
          </div>

          <button class="new-chat-button" type="button" @click="newConversation">
            New chat
          </button>
          <div class="conversation-list">
            <button
              v-for="conversation in conversations"
              :key="conversation.id"
              class="conversation-item"
              :class="{ active: conversation.id === currentConversationId }"
              type="button"
              @click="selectConversation(conversation.id)"
            >
              {{ conversation.title }}
            </button>
          </div>
        </aside>

        <div v-if="activeView === 'chat'" class="chat-column">
          <div ref="messagesContainer" class="messages">
            <article
              v-for="(message, index) in messages"
              :key="index"
              class="message"
              :class="message.role"
            >
              <div class="role">{{ message.role }}</div>
              <pre>{{ message.content }}</pre>
              <div
                v-if="message.role === 'assistant' && hasSources(message)"
                class="message-sources"
              >
                <div v-if="message.sources.length" class="source-list">
                  <details
                    v-for="source in message.sources"
                    :key="source.chunk_id || `${source.document_id}-${source.chunk_index}`"
                    class="source-item"
                  >
                    <summary>
                      <span class="source-label">[{{ source.label }}]</span>
                      <span class="source-document">{{ source.document_id }}</span>
                      <span class="source-meta">
                        chunk {{ source.chunk_index }} · score {{ formatScore(source.score) }}
                      </span>
                    </summary>
                    <p>{{ source.text }}</p>
                  </details>
                </div>
                <p v-else-if="message.content" class="source-empty">
                  本回答未使用知识库来源
                </p>
              </div>
            </article>
          </div>

          <p v-if="error" class="error">{{ error }}</p>

          <form class="composer" @submit.prevent="sendMessageStream">
            <textarea
              v-model="input"
              rows="3"
              placeholder="Type a message..."
              @keydown.enter.exact.prevent="sendMessageStream"
            />
            <button type="submit" :disabled="loading || !input.trim()">
              {{ loading ? "Sending" : "Send" }}
            </button>
          </form>
        </div>

        <div v-else class="knowledge-column">
          <section class="knowledge-section">
            <div class="section-header">
              <div>
                <h2>Knowledge</h2>
                <p>Upload Markdown or text files into vector search. Max file size: 50MB.</p>
              </div>
            </div>

            <form class="index-form" @submit.prevent="uploadKnowledgeFile">
              <input
                ref="knowledgeFileInput"
                class="hidden-file-input"
                type="file"
                accept=".md,.txt,text/markdown,text/plain"
                @change="onKnowledgeFileChange"
              />
              <div class="selected-file">
                <strong>{{ selectedKnowledgeFile ? selectedKnowledgeFile.name : "No file selected" }}</strong>
                <span v-if="selectedKnowledgeFile">
                  {{ (selectedKnowledgeFile.size / 1024 / 1024).toFixed(2) }} MB
                </span>
              </div>
              <button class="secondary-button file-button" type="button" @click="chooseKnowledgeFile">
                Browse
              </button>
              <label class="notes-field">
                <span>Notes</span>
                <textarea
                  v-model="knowledgeNotes"
                  rows="3"
                  placeholder="Optional context for this document"
                />
              </label>
              <button type="submit" :disabled="knowledgeLoading || !selectedKnowledgeFile">
                {{ knowledgeLoading ? "Uploading" : "Upload" }}
              </button>
            </form>

            <p v-if="knowledgeError" class="error knowledge-error">{{ knowledgeError }}</p>

            <form class="knowledge-search-form" @submit.prevent="searchKnowledge">
              <label>
                <span>Search test</span>
                <input
                  v-model="knowledgeSearchQuery"
                  placeholder="Test a question against indexed knowledge"
                />
              </label>
              <button type="submit" :disabled="knowledgeSearchLoading || !knowledgeSearchQuery.trim()">
                {{ knowledgeSearchLoading ? "Searching" : "Search" }}
              </button>
            </form>

            <p v-if="knowledgeSearchError" class="error knowledge-error">
              {{ knowledgeSearchError }}
            </p>

            <div v-if="knowledgeSearchResults.length" class="search-result-list">
              <article
                v-for="result in knowledgeSearchResults"
                :key="result.chunk_id"
                class="search-result-item"
              >
                <div class="search-result-meta">
                  <strong>{{ result.document_id }}</strong>
                  <span>#{{ result.chunk_index }}</span>
                  <span>score {{ formatScore(result.score) }}</span>
                </div>
                <p>{{ result.text }}</p>
              </article>
            </div>

            <p
              v-else-if="knowledgeSearchQuery.trim() && !knowledgeSearchLoading && !knowledgeSearchError"
              class="empty-state search-empty"
            >
              No matching chunks above score 0.300.
            </p>

            <div class="document-list">
              <article
                v-for="document in knowledgeDocuments"
                :key="document.document_id"
                class="document-item"
              >
                <div>
                  <h3>{{ document.document_id }}</h3>
                  <p>
                    {{ document.chunk_count }} chunks
                    <span v-if="document.updated_at"> · {{ formatDate(document.updated_at) }}</span>
                  </p>
                  <p v-if="document.notes" class="document-notes">{{ document.notes }}</p>
                </div>
                <button
                  class="danger-button"
                  type="button"
                  :disabled="knowledgeLoading"
                  @click="deleteKnowledgeDocument(document.document_id)"
                >
                  Delete
                </button>
              </article>

              <p v-if="knowledgeDocuments.length === 0" class="empty-state">
                No indexed documents.
              </p>
            </div>
          </section>
        </div>
      </div>

      <p v-if="!isAuthenticated && error" class="error">{{ error }}</p>
    </section>
  </main>
</template>
