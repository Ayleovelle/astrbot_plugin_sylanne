/// <reference types="node" />

import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const sourceRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function source(...parts: string[]): string {
  return readFileSync(resolve(sourceRoot, ...parts), 'utf8')
}

describe('Task 14 scoped admin controls', () => {
  it('shows capacity state without day-based retention wording', () => {
    const chamber = source('components', 'monitor', 'ObservationChamber.vue')
    const i18n = source('composables', 'useI18n.ts')

    expect(chamber).toContain('budget_unsatisfiable')
    expect(chamber).toContain('cleanup_active')
    expect(chamber).toContain("t('observation.cleanup_active')")
    expect(chamber).toContain("t('observation.budget_unsatisfiable')")
    expect(i18n).toContain('受保护数据无法在当前容量内继续清理')
    expect(`${chamber}\n${i18n}`).not.toMatch(/(?:7\s*天|七天|7\s*days?|retention\s*days?)/i)
  })

  it('uses fenced scoped copy-claim and renders only shortened legacy identifiers', () => {
    const admin = source('views', 'AdminView.vue')

    expect(admin).toContain("apiFetch<LegacyInventoryResponse>('/api/v1/legacy/inventory')")
    expect(admin).toContain("scopedApiFetch(snapshot, 'legacy-claim'")
    expect(admin).toContain('scope.isCurrent(snapshot, response)')
    expect(admin).toContain('scope.selectionEpoch')
    expect(admin).toContain('clearScopeData')
    expect(admin).toContain('shortValue(record.record_id)')
    expect(admin).toContain('shortValue(record.checksum)')
    expect(admin).not.toMatch(/(?:delete|mutate|prompt|umo|self_id|platform|address)/i)
  })

  it('shows delivery badges from fenced live state in Admin and Logs', () => {
    const admin = source('views', 'AdminView.vue')
    const logs = source('views', 'LogsView.vue')

    expect(admin).toContain('live.state?.delivery')
    expect(logs).toContain('live.state?.delivery')
    expect(logs).not.toContain("scopedApiFetch<ScopedStateResponse>")
    expect(`${admin}\n${logs}`).toContain('delivery_outcome_unknown')
    expect(`${admin}\n${logs}`).toContain('account_route_unavailable')
  })
})
