<script setup>
import LoginPanel from "./components/LoginPanel.vue";
import WorkspaceView from "./views/WorkspaceView.vue";
import { useAppController } from "./useAppController";

const {
  username,
  password,
  authLoading,
  isAuthenticated,
  isAdmin,
  currentUser,
  activeView,
  chatAdmissionLabel,
  shouldShowDailyTokenWarning,
  shouldShowDeepseekBalance,
  formatNumber,
  todayTokenTotal,
  balanceError,
  deepseekBalance,
  formatDeepseekBalance,
  settingsMenu,
  closeSettingsMenu,
  openTokenMonitor,
  openOperationsOverview,
  logout,
  login,
  error,
  workspaceBindings,
} = useAppController();
</script>
<template>
  <main class="app-shell">
    <section class="chat-panel">
      <header class="toolbar">
        <div>
          <h1>RAG</h1>
          <p>{{ isAuthenticated ? "AI agent" : "Sign in to continue" }}</p>
        </div>
        <div class="session">
          <span
            v-if="isAuthenticated && isAdmin"
            class="chat-capacity-status"
            title="在线用户数"
          >
            {{ chatAdmissionLabel }}
          </span>
          <span
            v-if="isAuthenticated && shouldShowDailyTokenWarning()"
            class="token-warning-status"
            :title="`Today token usage: ${formatNumber(todayTokenTotal())}`"
          >
            Token high
          </span>
          <span
            v-if="isAuthenticated && isAdmin && shouldShowDeepseekBalance"
            class="balance-status"
            :class="{ unavailable: balanceError || deepseekBalance?.is_available === false }"
          >
            {{ formatDeepseekBalance() }}
          </span>
          <details v-if="isAuthenticated" ref="settingsMenu" class="settings-menu">
            <summary class="status" title="Account menu" aria-label="Account menu">
              {{ currentUser }}
            </summary>
            <div class="settings-menu-panel">
              <button
                v-if="isAdmin"
                type="button"
                :class="{ active: activeView === 'knowledge' }"
                @click="activeView = 'knowledge'; closeSettingsMenu()"
              >
                Knowledge
              </button>
              <button
                v-if="isAdmin"
                type="button"
                :class="{ active: activeView === 'users' }"
                @click="activeView = 'users'; closeSettingsMenu()"
              >
                Users
              </button>
              <button
                v-if="isAdmin"
                type="button"
                :class="{ active: activeView === 'token-monitor' }"
                @click="openTokenMonitor"
              >
                Token Monitor
              </button>
              <button
                v-if="isAdmin"
                type="button"
                :class="{ active: activeView === 'operations' }"
                @click="activeView = 'operations'; openOperationsOverview(); closeSettingsMenu()"
              >
                Operations
              </button>
              <button
                class="logout-menu-button"
                type="button"
                :disabled="authLoading"
                @click="closeSettingsMenu(); logout()"
              >
                Logout
              </button>
            </div>
          </details>
        </div>
      </header>

      <LoginPanel
        v-if="!isAuthenticated"
        v-model:username="username"
        v-model:password="password"
        :auth-loading="authLoading"
        @login="login"
      />

      <WorkspaceView v-else :b="workspaceBindings" />

      <p v-if="!isAuthenticated && error" class="error">{{ error }}</p>
    </section>
  </main>
</template>

<style scoped>
.conversation-item {
  text-align: left;
}

.conversation-title {
  font-weight: 500;
  margin-bottom: 4px;
}

.conversation-time {
  font-size: 11px;
  color: #888;
}
</style>
