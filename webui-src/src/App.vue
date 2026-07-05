<script setup lang="ts">
// Root: the router renders either the LoginView or the DashboardLayout shell.
// BootScreen (the SYSTEM INIT cover) and VoidVeil (the cross-route void
// handoff) are mounted here, ONCE, above RouterView — see
// composables/useBoot.ts + useVoidTransition.ts.
import BootScreen from './components/BootScreen.vue'
import VoidVeil from './components/VoidVeil.vue'
</script>

<template>
  <!-- BootScreen mounts FIRST (mount order = template order): its release
       timers must be registered before any sibling's mounted hook can throw
       and abort the post-flush queue (Vue dev rethrow), or the cover would
       cover a dead app forever. Stacking is z-index-driven, so DOM order
       doesn't affect visuals (boot z-50000 > veil > page). -->
  <BootScreen />
  <RouterView />
  <VoidVeil />
</template>
