<script setup>
defineProps({
  conversations: {
    type: Array,
    required: true,
  },
  currentConversationId: {
    type: [Number, String, null],
    default: null,
  },
  formatDate: {
    type: Function,
    required: true,
  },
});

defineEmits(["new-chat", "open-conversation"]);
</script>

<template>
  <aside class="sidebar">
    <button class="new-chat-button" type="button" @click="$emit('new-chat')">
      New chat
    </button>
    <div class="conversation-list">
      <button
        v-for="conversation in conversations"
        :key="conversation.id"
        class="conversation-item"
        :class="{ active: conversation.id === currentConversationId }"
        type="button"
        @click="$emit('open-conversation', conversation.id)"
      >
        <div class="conversation-title">{{ conversation.title }}</div>
        <div v-if="conversation.updated_at" class="conversation-time">
          {{ formatDate(conversation.updated_at) }}
        </div>
      </button>
    </div>
  </aside>
</template>
