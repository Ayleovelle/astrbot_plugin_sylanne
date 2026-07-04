import { ref } from 'vue'

// Models the login<->dashboard "void" transition as a small FSM, ported from
// the old UI's voidTransitionState/Start/Duration/Callback globals
// (UI/index.html ~773-994). SpecimenCanvas reads state/progress every frame;
// LoginView (and later a logout flow) drive it via start().

export type VoidDirection = 'expanding' | 'shrinking'
export type VoidState = 'idle' | VoidDirection

// Module-level singleton — shared across every caller (mirrors useTheme.ts).
const state = ref<VoidState>('idle')
const progress = ref(0)

// Guards overlapping start() calls: while a transition is in flight, further
// calls get the same promise back instead of racing a second rAF ticker.
let activePromise: Promise<void> | null = null

export function useVoidTransition() {
  function start(direction: VoidDirection, durationMs = 1600): Promise<void> {
    if (activePromise) return activePromise

    state.value = direction
    progress.value = 0

    activePromise = new Promise<void>((resolve) => {
      const startedAt = performance.now()

      function tick(now: number): void {
        const elapsed = now - startedAt
        progress.value = Math.min(elapsed / durationMs, 1)

        if (progress.value >= 1) {
          state.value = 'idle'
          activePromise = null
          resolve()
          return
        }
        requestAnimationFrame(tick)
      }

      requestAnimationFrame(tick)
    })

    return activePromise
  }

  return { state, progress, start }
}
