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
