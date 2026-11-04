import type { ScenarioDefinition, TwinRunPayload, TwinSnapshot } from './types'

export type RoutePage = 'overview' | 'components' | 'evidence' | 'assistant'
export type EngineStatus = 'checking' | 'connected' | 'offline'
export type ThemePreference = 'system' | 'light' | 'dark'

export function parseRoute(hash: string): { page: RoutePage; componentId?: string } {
  const path = hash.replace(/^#\/?/, '').split('?')[0]
  if (path === 'evidence') return { page: 'evidence' }
  if (path === 'assistant') return { page: 'assistant' }
  if (path === 'components' || path.startsWith('components/')) {
    return { page: 'components', componentId: path.split('/')[1] }
  }
  return { page: 'overview' }
}

export function getBoundaryDetails({
  run,
  snapshot,
  scenario,
  scenarioId,
}: {
  run: TwinRunPayload | null
  snapshot: TwinSnapshot | null
  scenario: ScenarioDefinition | undefined
  scenarioId: string
}): { modelName: string; provenance: string; scenario: string } {
  return {
    modelName: run?.run.model_name ?? 'Simplified open-cycle reference model',
    provenance: snapshot?.data_provenance ?? 'Locally generated synthetic operating data.',
    scenario: scenario?.name ?? scenarioId,
  }
}
