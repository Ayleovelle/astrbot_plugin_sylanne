<script setup lang="ts">
// Root: the router renders either the LoginView or the DashboardLayout shell.
// BootScreen (the SYSTEM INIT cover) is mounted here once above RouterView.
import BootScreen from './components/BootScreen.vue'
</script>

<template>
  <!-- BootScreen mounts FIRST (mount order = template order): its release
       timers must be registered before any sibling's mounted hook can throw
       and abort the post-flush queue (Vue dev rethrow), or the cover would
       cover a dead app forever. Stacking is z-index-driven, so DOM order
       doesn't affect visuals. -->
  <BootScreen />
  <RouterView />
</template>
