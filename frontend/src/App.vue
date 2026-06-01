<script setup>
import { ref } from "vue";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

const input = ref("");
const username = ref("");
const password = ref("");
const currentUser = ref("");
const loading = ref(false);
const authLoading = ref(false);
const error = ref("");
const messages = ref([
  {
    role: "assistant",
    content: "Ask about project files, code, or tool behavior.",
  },
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
    password.value = "";
    authLoading.value = false;
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
      body: JSON.stringify({ message: text }),
    });

    if (!response.ok) {
      throw new Error(`Request failed with status ${response.status}`);
    }

    const data = await response.json();
    messages.value.push({ role: "assistant", content: data.answer || "" });
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
          <h1>AI Agent</h1>
          <p>Vue 3 + FastAPI</p>
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

      <form v-if="!isAuthenticated" class="login-form" @submit.prevent="login">
        <label>
          <span>Username</span>
          <input v-model="username" autocomplete="username" />
        </label>
        <label>
          <span>Password</span>
          <input v-model="password" type="password" autocomplete="current-password" />
        </label>
        <button type="submit" :disabled="authLoading || !username.trim() || !password">
          {{ authLoading ? "Signing in" : "Login" }}
        </button>
      </form>

      <div v-else class="messages">
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

      <form v-if="isAuthenticated" class="composer" @submit.prevent="sendMessage">
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
    </section>
  </main>
</template>
