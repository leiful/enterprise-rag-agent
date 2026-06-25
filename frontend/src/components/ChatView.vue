<script setup>
import { ref } from "vue";

defineProps({
  conversationLoading: {
    type: Boolean,
    required: true,
  },
  messages: {
    type: Array,
    required: true,
  },
  error: {
    type: String,
    default: "",
  },
  loading: {
    type: Boolean,
    required: true,
  },
  input: {
    type: String,
    required: true,
  },
  feedbackOptions: {
    type: Function,
    required: true,
  },
  feedbackTypeLabel: {
    type: Function,
    required: true,
  },
  hasSources: {
    type: Function,
    required: true,
  },
  referencedSources: {
    type: Function,
    required: true,
  },
  formatDate: {
    type: Function,
    required: true,
  },
  formatSourceName: {
    type: Function,
    required: true,
  },
  formatScore: {
    type: Function,
    required: true,
  },
  formatPageRange: {
    type: Function,
    required: true,
  },
});

defineEmits(["send", "submit-feedback", "update:input"]);

const messagesContainer = ref(null);

function scrollToBottom() {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
  }
}

defineExpose({ scrollToBottom });
</script>

<template>
  <div class="chat-column">
    <div ref="messagesContainer" class="messages">
      <div v-if="conversationLoading" class="message-skeleton-list" aria-hidden="true">
        <div class="message-skeleton">
          <span></span>
          <strong></strong>
          <em></em>
        </div>
        <div class="message-skeleton user">
          <span></span>
          <strong></strong>
        </div>
        <div class="message-skeleton">
          <span></span>
          <strong></strong>
          <em></em>
        </div>
      </div>
      <article
        v-if="!conversationLoading"
        v-for="(message, index) in messages"
        :key="index"
        class="message"
        :class="message.role"
      >
        <div class="message-header">
          <span class="role">{{ message.role }}</span>
          <span v-if="message.created_at" class="message-time">{{ formatDate(message.created_at) }}</span>
        </div>
        <pre>{{ message.content }}</pre>
        <div
          v-if="message.role === 'assistant' && message.content && index > 0 && !message.isTyping"
          class="message-feedback"
        >
          <button
            v-for="type in feedbackOptions(message)"
            :key="type"
            class="feedback-button"
            type="button"
            :disabled="message.feedbackLoading"
            @click="$emit('submit-feedback', message, index, type)"
          >
            {{ feedbackTypeLabel(type) }}
          </button>
          <span v-if="message.feedbackSent" class="feedback-saved">
            Saved: {{ feedbackTypeLabel(message.feedbackSent) }}
          </span>
          <span v-if="message.feedbackError" class="feedback-error">
            {{ message.feedbackError }}
          </span>
        </div>
        <div
          v-if="message.role === 'assistant' && hasSources(message) && !message.isTyping"
          class="message-sources"
        >
          <div v-if="referencedSources(message).length" class="source-list">
            <details
              v-for="source in referencedSources(message)"
              :key="source.chunk_id || `${source.document_id}-${source.chunk_index}`"
              class="source-item"
            >
              <summary>
                <span class="source-label">[{{ source.label }}]</span>
                <span class="source-document" :title="source.document_id || ''">
                  {{ formatSourceName(source.document_id) }}
                </span>
                <span class="source-meta">
                  chunk {{ source.chunk_index }} / score {{ formatScore(source.score) }}
                </span>
                <span class="source-meta-readable">
                  chunk {{ source.chunk_index }}
                  <template v-if="formatPageRange(source)"> / {{ formatPageRange(source) }}</template>
                  / score {{ formatScore(source.score) }}
                </span>
                <span class="source-meta-clean">
                  chunk {{ source.chunk_index }}
                  <template v-if="formatPageRange(source)"> | {{ formatPageRange(source) }}</template>
                  | score {{ formatScore(source.score) }}
                </span>
              </summary>
              <p>{{ source.text }}</p>
            </details>
          </div>
          <p v-else-if="message.content" class="source-empty">
            本回答未使用知识库来源。
          </p>
        </div>
      </article>
    </div>

    <p v-if="error" class="error">{{ error }}</p>

    <form class="composer" @submit.prevent="$emit('send')">
      <textarea
        :value="input"
        rows="3"
        placeholder="Type a message..."
        :disabled="conversationLoading"
        @input="$emit('update:input', $event.target.value)"
        @keydown.enter.exact.prevent="$emit('send')"
      />
      <button type="submit" :disabled="loading || conversationLoading || !input.trim()">
        {{ loading ? "Sending" : "Send" }}
      </button>
    </form>
  </div>
</template>
