import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { fetchScopeCatalog } from '../api/client'
import type {
  ScopeCatalogEntry,
  ScopeCatalogResponse,
  ScopeRequestSnapshot,
  ScopedApiResponse,
  ScopeSelection,
} from '../api/types'

const STORAGE_KEY = 'sylanne_scope_selection_v1'

const EMPTY_SELECTION: ScopeSelection = {
  botRef: '',
  personaRef: '',
  sessionRef: '',
}

function sameSelection(left: ScopeSelection, right: ScopeSelection): boolean {
  return (
    left.botRef === right.botRef &&
    left.personaRef === right.personaRef &&
    left.sessionRef === right.sessionRef
  )
}

function unique(values: string[]): string[] {
  return [...new Set(values)]
}

function readStoredSelection(): ScopeSelection {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || '') as {
      schema?: unknown
      selection?: Partial<ScopeSelection>
    }
    const selection = parsed.schema === 1 ? parsed.selection : undefined
    if (
      typeof selection?.botRef === 'string' &&
      typeof selection.personaRef === 'string' &&
      typeof selection.sessionRef === 'string'
    ) {
      return {
        botRef: selection.botRef,
        personaRef: selection.personaRef,
        sessionRef: selection.sessionRef,
      }
    }
  } catch {
    // A malformed persisted choice must never select an arbitrary scope.
  }
  return { ...EMPTY_SELECTION }
}

function persistSelection(selection: ScopeSelection): void {
  try {
    if (selection.botRef && selection.personaRef && selection.sessionRef) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ schema: 1, selection }))
    } else {
      localStorage.removeItem(STORAGE_KEY)
    }
  } catch {
    // Storage is only a convenience; the authoritative scope is the catalog.
  }
}

function matchingEntry(
  entries: ScopeCatalogEntry[],
  selection: ScopeSelection,
): ScopeCatalogEntry | undefined {
  if (!selection.botRef || !selection.personaRef || !selection.sessionRef) return undefined
  return entries.find(
    (entry) =>
      entry.scope.bot_ref === selection.botRef &&
      entry.scope.persona_ref === selection.personaRef &&
      entry.scope.session_ref === selection.sessionRef,
  )
}

function reconciledSelection(
  entries: ScopeCatalogEntry[],
  previous: ScopeSelection,
): ScopeSelection {
  const bots = unique(entries.map((entry) => entry.scope.bot_ref))
  const botRef = bots.includes(previous.botRef)
    ? previous.botRef
    : bots.length === 1
      ? bots[0]
      : ''
  if (!botRef) return { ...EMPTY_SELECTION }

  const personas = unique(
    entries
      .filter((entry) => entry.scope.bot_ref === botRef)
      .map((entry) => entry.scope.persona_ref),
  )
  const personaRef = personas.includes(previous.personaRef)
    ? previous.personaRef
    : personas.length === 1
      ? personas[0]
      : ''
  if (!personaRef) return { botRef, personaRef: '', sessionRef: '' }

  const sessions = unique(
    entries
      .filter(
        (entry) =>
          entry.scope.bot_ref === botRef && entry.scope.persona_ref === personaRef,
      )
      .map((entry) => entry.scope.session_ref),
  )
  const sessionRef = sessions.includes(previous.sessionRef)
    ? previous.sessionRef
    : sessions.length === 1
      ? sessions[0]
      : ''
  return { botRef, personaRef, sessionRef }
}

export const useScopeStore = defineStore('scope', () => {
  const catalog = ref<ScopeCatalogEntry[]>([])
  const selection = ref<ScopeSelection>(readStoredSelection())
  const selectionEpoch = ref(0)

  const selectedEntry = computed(() => matchingEntry(catalog.value, selection.value))
  const selectedScopeGeneration = computed<number | null>(
    () => selectedEntry.value?.generations.scope ?? null,
  )
  const bots = computed(() => unique(catalog.value.map((entry) => entry.scope.bot_ref)))
  const personas = computed(() =>
    selection.value.botRef
      ? unique(
          catalog.value
            .filter((entry) => entry.scope.bot_ref === selection.value.botRef)
            .map((entry) => entry.scope.persona_ref),
        )
      : [],
  )
  const sessions = computed(() =>
    selection.value.botRef && selection.value.personaRef
      ? unique(
          catalog.value
            .filter(
              (entry) =>
                entry.scope.bot_ref === selection.value.botRef &&
                entry.scope.persona_ref === selection.value.personaRef,
            )
            .map((entry) => entry.scope.session_ref),
        )
      : [],
  )

  function setSelection(next: ScopeSelection): void {
    if (sameSelection(selection.value, next)) return
    selection.value = next
    selectionEpoch.value += 1
    persistSelection(next)
  }

  function setCatalog(response: ScopeCatalogResponse): void {
    const previousGeneration = selectedScopeGeneration.value
    catalog.value = Array.isArray(response.scopes) ? response.scopes : []
    const next = reconciledSelection(catalog.value, selection.value)
    const changedSelection = !sameSelection(selection.value, next)
    const nextGeneration = matchingEntry(catalog.value, next)?.generations.scope ?? null
    if (changedSelection) {
      selection.value = next
      persistSelection(next)
    }
    if (changedSelection || previousGeneration !== nextGeneration) {
      selectionEpoch.value += 1
    }
  }

  async function refreshCatalog(): Promise<void> {
    setCatalog(await fetchScopeCatalog())
  }

  function selectBot(botRef: string): void {
    if (!bots.value.includes(botRef)) return
    if (selection.value.botRef === botRef) return
    setSelection({ botRef, personaRef: '', sessionRef: '' })
  }

  function selectPersona(personaRef: string): void {
    if (!selection.value.botRef || !personas.value.includes(personaRef)) return
    if (selection.value.personaRef === personaRef) return
    setSelection({
      botRef: selection.value.botRef,
      personaRef,
      sessionRef: '',
    })
  }

  function selectSession(sessionRef: string): void {
    if (
      !selection.value.botRef ||
      !selection.value.personaRef ||
      !sessions.value.includes(sessionRef)
    ) {
      return
    }
    setSelection({
      botRef: selection.value.botRef,
      personaRef: selection.value.personaRef,
      sessionRef,
    })
  }

  function snapshot(): ScopeRequestSnapshot | null {
    const generation = selectedScopeGeneration.value
    if (!selectedEntry.value || generation === null) return null
    return {
      selection: {
        botRef: selection.value.botRef,
        personaRef: selection.value.personaRef,
        sessionRef: selection.value.sessionRef,
      },
      selectionEpoch: selectionEpoch.value,
      scopeGeneration: generation,
    }
  }

  function isCurrent(snapshotValue: ScopeRequestSnapshot, response?: ScopedApiResponse): boolean {
    const current = snapshot()
    if (
      !current ||
      current.selectionEpoch !== snapshotValue.selectionEpoch ||
      current.scopeGeneration !== snapshotValue.scopeGeneration ||
      !sameSelection(current.selection, snapshotValue.selection)
    ) {
      return false
    }
    if (!response) return true
    const scope = response.scope
    const generation = response.scope_generation ?? response.generations?.scope
    return (
      scope?.bot_ref === snapshotValue.selection.botRef &&
      scope.persona_ref === snapshotValue.selection.personaRef &&
      scope.session_ref === snapshotValue.selection.sessionRef &&
      generation === snapshotValue.scopeGeneration
    )
  }

  return {
    catalog,
    selection,
    selectionEpoch,
    selectedScopeGeneration,
    bots,
    personas,
    sessions,
    setCatalog,
    refreshCatalog,
    selectBot,
    selectPersona,
    selectSession,
    snapshot,
    isCurrent,
  }
})
