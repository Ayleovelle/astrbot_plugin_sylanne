<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { RouterView } from 'vue-router'
import SpineNav from './SpineNav.vue'
import TopBar from './TopBar.vue'
import AppFooter from './AppFooter.vue'
import { useLiveStore } from '../../stores/live'

// The shell owns the shared /api/state poll for its whole lifetime, so every
// dashboard page just reads useLiveStore().state.
const live = useLiveStore()
onMounted(() => live.start(5000))
onUnmounted(() => live.stop())
</script>

<template>
  <div class="layout">
    <SpineNav class="area-nav" />
    <TopBar class="area-top" />
    <main class="area-content">
      <RouterView />
    </main>
    <AppFooter class="area-foot" />
  </div>
</template>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: var(--nav-w) 1fr;
  grid-template-rows: var(--header-h) 1fr var(--footer-h);
  height: 100vh;
}
.area-nav {
  grid-column: 1;
  grid-row: 1 / -1;
}
.area-top {
  grid-column: 2;
  grid-row: 1;
}
.area-content {
  grid-column: 2;
  grid-row: 2;
  overflow-y: auto;
  padding: var(--space-8);
  /* faint instrument ambiance so the field isn't a dead-flat --bg */
  background:
    radial-gradient(ellipse 120% 70% at 50% -10%, rgba(184, 138, 158, 0.04), transparent 55%),
    radial-gradient(ellipse 90% 60% at 50% 120%, rgba(0, 0, 0, 0.25), transparent 60%);
}
.area-foot {
  grid-column: 2;
  grid-row: 3;
}

@media (max-width: 720px) {
  .layout {
    grid-template-columns: 56px 1fr;
  }
}
</style>
