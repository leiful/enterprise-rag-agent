<script setup>
import { ref } from "vue";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
const API_KEY = import.meta.env.VITE_APP_API_KEY || "";

const input = ref("");
const loading = ref(false);
const error = ref("");
const messages = ref([
  {
    role: "assistant",
    content: "Ask about project files, code, or tool behavior.",
  },
]);

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
        "X-API-Key": API_KEY,
      },
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
</script>

<template>
  <main class="app-shell">
    <section class="chat-panel">
      <header class="toolbar">
        <div>
          <h1>AI Agent</h1>
          <p>Vue 3 + FastAPI</p>
        </div>
        <span class="status">Local</span>
      </header>

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
    </section>
  </main>
</template>
