import type { ScenarioDefinition, TwinRunPayload, TwinSnapshot } from './types'
export type { RoutePage, ThemePreference } from './app/router'
export type EngineStatus = 'checking' | 'connected' | 'offline'

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
