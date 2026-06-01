<script setup>
import { ref } from "vue";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

const input = ref("");
const username = ref("");
const password = ref("");
const currentUser = ref("");
const conversations = ref([]);
const currentConversationId = ref(null);
const loading = ref(false);
const authLoading = ref(false);
const error = ref("");
const emptyMessage = {
  role: "assistant",
  content: "Ready. Ask me to inspect project files, explain code, or run safe checks.",
};
const messages = ref([
  emptyMessage,
]);

const isAuthenticated = ref(false);

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
    }));

    if (messages.value.length === 0) {
      messages.value = [emptyMessage];
    }
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
    messages.value.push({ role: "assistant", content: data.answer || "" });
    await loadConversations();
  } catch (err) {
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

        <div class="chat-column">
          <div class="messages">
            <article
              v-for="(message, index) in messages"
              :key="index"
              class="message"
              :class="message.role"
            >
              <div class="role">{{ message.role }}</div>
              <pre>{{ message.content }}</pre>
            </article>
          </div>

          <p v-if="error" class="error">{{ error }}</p>

          <form class="composer" @submit.prevent="sendMessage">
            <textarea
              v-model="input"
              rows="3"
              placeholder="Type a message..."
              @keydown.enter.exact.prevent="sendMessage"
            />
            <button type="submit" :disabled="loading || !input.trim()">
              {{ loading ? "Sending" : "Send" }}
            </button>
          </form>
        </div>
      </div>

      <p v-if="!isAuthenticated && error" class="error">{{ error }}</p>
    </section>
  </main>
</template>
