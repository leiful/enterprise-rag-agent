<script setup>
defineProps({
  username: {
    type: String,
    required: true,
  },
  password: {
    type: String,
    required: true,
  },
  authLoading: {
    type: Boolean,
    required: true,
  },
});

defineEmits(["login", "update:username", "update:password"]);
</script>

<template>
  <div class="login-view">
    <div class="login-copy">
      <p class="eyebrow">Secure access</p>
      <h2>Open your agent workspace</h2>
      <p>Use your server account to continue.</p>
    </div>

    <form class="login-form" @submit.prevent="$emit('login')">
      <label>
        <span>Username</span>
        <input
          :value="username"
          autocomplete="username"
          placeholder="admin"
          @input="$emit('update:username', $event.target.value)"
        />
      </label>
      <label>
        <span>Password</span>
        <input
          :value="password"
          type="password"
          autocomplete="current-password"
          placeholder="Enter password"
          @input="$emit('update:password', $event.target.value)"
        />
      </label>
      <button type="submit" :disabled="authLoading || !username.trim() || !password">
        {{ authLoading ? "Signing in" : "Sign in" }}
      </button>
    </form>
  </div>
</template>
