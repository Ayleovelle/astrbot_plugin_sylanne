<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from '../../composables/useI18n'
import { useTheme, useLang } from '../../composables/useTheme'
import { useAuthStore } from '../../stores/auth'
import { useSessionStore, sessionId, sessionLabel } from '../../stores/session'
import { useLiveStore } from '../../stores/live'

const router = useRouter()
const { t } = useI18n()
const { theme, toggleTheme } = useTheme()
const { lang, toggleLang } = useLang()
const auth = useAuthStore()
const session = useSessionStore()
const live = useLiveStore()

const online = computed(() => !!live.state && !live.error)

function onSessionChange(e: Event): void {
  const id = (e.target as HTMLSelectElement).value
  session.setCurrent(id)
  void live.fetchOnce()
}
function logout(): void {
  auth.logout()
  void router.replace({ name: 'login' })
}
</script>

<template>
  <header class="top">
    <div class="brand">
      <span class="brand-name">SYLANNE</span>
      <span class="brand-sub">{{ t('app.title') }}</span>
    </div>

    <div class="controls">
      <span class="status" :class="{ on: online }">
        <i class="status-dot" />
        {{ online ? t('chrome.online') : t('chrome.offline') }}
      </span>

      <select
        v-if="session.sessions.length"
        class="session-pill mono"
        :value="session.current"
        :title="t('chrome.session')"
        @change="onSessionChange"
      >
        <option
          v-for="s in session.sessions"
          :key="sessionId(s)"
          :value="sessionId(s)"
        >
          {{ sessionLabel(s) }}
        </option>
      </select>

      <button class="chip" :title="t('chrome.theme')" @click="toggleTheme">
        {{ theme === 'dark' ? '☾' : '☀' }}
      </button>
      <button class="chip mono" :title="t('chrome.lang')" @click="toggleLang">
        {{ lang === 'zh' ? '中' : 'EN' }}
      </button>
      <button class="chip" :title="t('chrome.logout')" @click="logout">⏻</button>
    </div>
  </header>
</template>

<style scoped>
.top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--space-8);
  border-bottom: 1px solid var(--card-border);
}
.brand {
  display: flex;
  align-items: baseline;
  gap: var(--space-4);
}
.brand-name {
  font-size: var(--font-md);
  font-weight: 700;
  letter-spacing: 3px;
  color: var(--accent);
}
.brand-sub {
  font-size: var(--font-xs);
  letter-spacing: 2px;
  color: var(--text-muted);
}
.controls {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}
.status {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-xs);
  letter-spacing: 1px;
  color: var(--text-muted);
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-muted);
}
.status.on .status-dot {
  background: var(--green);
  animation: dotBreath 3.2s ease-in-out infinite;
}
.session-pill {
  background: var(--card);
  border: 1px solid var(--card-border);
  border-radius: var(--r-pill);
  color: var(--text);
  font-size: var(--font-xs);
  padding: var(--space-2) var(--space-5);
  max-width: 200px;
  cursor: pointer;
}
.chip {
  background: var(--card);
  border: 1px solid var(--card-border);
  border-radius: var(--r-pill);
  color: var(--text);
  width: 30px;
  height: 26px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-sm);
  transition: border-color var(--dur-fast) ease;
}
.chip:hover {
  border-color: var(--accent);
}
</style>
