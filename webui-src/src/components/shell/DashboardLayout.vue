<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import SpineNav from './SpineNav.vue'
import TopBar from './TopBar.vue'
import AppFooter from './AppFooter.vue'
import { useLiveStore } from '../../stores/live'
import { useBoot } from '../../composables/useBoot'

// The shell owns the shared /api/state poll for its whole lifetime, so every
// dashboard page just reads useLiveStore().state.
const live = useLiveStore()
onMounted(() => live.start(5000))
onUnmounted(() => live.stop())

// ── Arrival choreography (old transitionToDashboard entrance, UI/index.html
// ~2028-2040): header slides down, footer slides up, spine nodes fade in,
// and the current page's cards fly in staggered by column. Fires ONCE, only
// when boot/LoginView flagged a real arrival — never on ordinary page nav.
const boot = useBoot()
const arriving = ref(false)
// Reactive consume instead of a one-shot mount check: on a welcome-back boot
// this layout mounts (under the boot cover) BEFORE the async verifyExisting()
// resolves and requests the arrival — a mount-time consume would race it and
// the entrance would never play. The watcher covers both orders: flag already
// set at mount (fresh login set it before router.replace) fires via
// immediate; flag set later (boot verify) fires when it flips.
watch(
  () => boot.arrivalPending.value,
  (pending) => {
    if (!pending || !boot.consumeArrival()) return
    arriving.value = true
    // Strip once every choreographed animation below has finished — longest
    // is the spine rail draw-in (1.2s) + its trailing node fade (0.9s delay
    // + 0.4s), so this must clear noticeably later than the cards' own
    // ~800ms, or the class would vanish mid-animation and pop the elements
    // to their resting state.
    setTimeout(() => {
      arriving.value = false
    }, 1400)
  },
  { immediate: true },
)

// ── Directional page-switch (old .content-slider filmstrip, UI/index.html
// ~285-289): navigating down the nav list slides the outgoing page up and
// brings the new one in from below; navigating up does the inverse.
const NAV_ORDER = ['monitor', 'cognition', 'config', 'logs', 'memory', 'personality', 'life', 'admin']
const route = useRoute()
const routeKey = computed(() => (typeof route.name === 'string' ? route.name : String(route.name ?? '')))

const transitionName = ref('page-down')
// `flush: 'pre'` (the default) runs this before the component re-renders, so
// transitionName is already correct by the time <Transition> reads it for
// the upcoming leave/enter pair.
watch(
  () => routeKey.value,
  (next, prev) => {
    const nextIndex = NAV_ORDER.indexOf(next)
    const prevIndex = NAV_ORDER.indexOf(prev ?? '')
    transitionName.value = nextIndex < prevIndex ? 'page-up' : 'page-down'
  },
)
</script>

<template>
  <div class="layout" :class="{ arrive: arriving }">
    <SpineNav class="area-nav" />
    <TopBar class="area-top" />
    <main class="area-content">
      <RouterView v-slot="{ Component }">
        <Transition :name="transitionName" mode="out-in">
          <component :is="Component" :key="routeKey" />
        </Transition>
      </RouterView>
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

/* ── Directional page-switch: a lighter-weight echo of the old vertical
 * filmstrip (.content-slider, 0.6s) — GPU-friendly transform/opacity only,
 * two ~.35s legs instead of one .6s slide since out-in runs them in series. */
.page-down-enter-active,
.page-down-leave-active,
.page-up-enter-active,
.page-up-leave-active {
  transition: transform 0.35s var(--ease-organic), opacity 0.35s var(--ease-organic);
}
.page-down-leave-to {
  transform: translateY(-20px);
  opacity: 0;
}
.page-down-enter-from {
  transform: translateY(20px);
  opacity: 0;
}
.page-up-leave-to {
  transform: translateY(20px);
  opacity: 0;
}
.page-up-enter-from {
  transform: translateY(-20px);
  opacity: 0;
}

/* ── Arrival choreography: fires once, only on a real login/welcome-back
 * arrival (never on ordinary nav) — old transitionToDashboard entrance,
 * UI/index.html ~2028-2040 + .app-header/.app-footer/.card animate-in. */
.arrive .area-top {
  animation: shellDropIn 0.6s var(--ease-snap) 0.1s backwards;
}
.arrive .area-foot {
  animation: shellRiseIn 0.6s var(--ease-snap) 0.1s backwards;
}
.arrive .area-nav :deep(.spine-line) {
  animation: spineDrawIn 1.2s var(--ease-organic) both;
}
.arrive .area-nav :deep(.node) {
  animation: fadeUp 0.4s var(--ease-organic) 0.9s backwards;
}
.arrive .area-content :deep(.card) {
  animation-name: cardFromLeft;
  animation-duration: 0.5s;
  animation-timing-function: var(--ease-snap);
  animation-fill-mode: backwards;
}
.arrive .area-content :deep(.card:nth-child(even)) {
  animation-name: cardFromRight;
}
.arrive .area-content :deep(.card:nth-child(2)) {
  animation-delay: 0.07s;
}
.arrive .area-content :deep(.card:nth-child(3)) {
  animation-delay: 0.14s;
}
.arrive .area-content :deep(.card:nth-child(4)) {
  animation-delay: 0.21s;
}
.arrive .area-content :deep(.card:nth-child(n + 5)) {
  animation-delay: 0.28s;
}

@keyframes shellDropIn {
  from {
    transform: translateY(-100%);
    opacity: 0;
  }
  to {
    transform: translateY(0);
    opacity: 1;
  }
}
@keyframes shellRiseIn {
  from {
    transform: translateY(100%);
    opacity: 0;
  }
  to {
    transform: translateY(0);
    opacity: 1;
  }
}
@keyframes spineDrawIn {
  from {
    clip-path: inset(0 0 100% 0);
  }
  to {
    clip-path: inset(0 0 0 0);
  }
}
@keyframes cardFromLeft {
  from {
    opacity: 0;
    transform: translateX(40px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}
@keyframes cardFromRight {
  from {
    opacity: 0;
    transform: translateX(-40px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}
</style>
