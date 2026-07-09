<script setup lang="ts">
import { computed } from 'vue'
import { useVoidTransition } from '../composables/useVoidTransition'

// Cross-route void handoff. Mounted ONCE in App.vue, above RouterView.
// LoginView drives it: after the specimen swallow ('expanding') ends solid,
// the veil snaps fully opaque (setVeilSolid(true)), router.replace() runs
// underneath it, and once the dashboard route has mounted, 'revealing'
// irises it back open — the dashboard surfaces as if from the same void
// that swallowed the login screen. Idle cost is zero: v-show removes it
// from the render path entirely when nothing is happening.
//
// The iris-open is a plain two-state CSS transition (closed/open), NOT a
// per-frame JS-computed clip-path — unlike the specimen canvas (which is
// exempt), this is a regular DOM element, so it must collapse under the
// global prefers-reduced-motion kill-switch in base.css same as everything
// else. useVoidTransition's start('revealing', ms) is still awaited by
// LoginView for sequencing, but the visual motion itself lives in CSS.

const { state, veilSolid } = useVoidTransition()

const revealing = computed(() => state.value === 'revealing')
const visible = computed(() => veilSolid.value || revealing.value)
// Closed (0% hole) whenever solid and not yet revealing; open once revealing
// starts. The CSS transition below animates between the two.
const open = computed(() => revealing.value)
</script>

<template>
  <div v-show="visible" class="void-veil" :class="{ open }" aria-hidden="true" />
</template>

<style scoped>
.void-veil {
  position: fixed;
  inset: 0;
  z-index: 40000;
  background: rgb(var(--void-solid));
  pointer-events: none;
  clip-path: circle(0% at 50% 50%);
  transition: clip-path 0.9s cubic-bezier(0.5, 0, 0.2, 1);
}
.void-veil.open {
  clip-path: circle(150% at 50% 50%);
}
</style>
