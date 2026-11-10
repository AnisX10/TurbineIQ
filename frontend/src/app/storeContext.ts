import { createContext } from 'react'
import type { Dispatch } from 'react'
import type { ComponentId, RouteState, ThemePreference } from './router'
import type { ScenarioDefinition, TwinRunPayload } from '../types'
import type { AssistantResponse } from '../types'

export interface AssistantContextSnapshot {
  scenarioId: string
  scenarioName: string
  seed: number
  sampleIndex: number
  componentId: ComponentId
  componentName: string
}

export interface AssistantTurn {
  id: number
  question: string
  context: AssistantContextSnapshot
  answer?: AssistantResponse
  partialAnswer?: string
  toolProgress?: string
  error?: string
  streaming: boolean
}

export interface TurbineState extends RouteState {
  seedInput: string
  run: TwinRunPayload | null
  scenarios: ScenarioDefinition[]
  theme: ThemePreference
  engineStatus: 'checking' | 'connected' | 'offline'
  loading: boolean
  requestError: string
  assistantOpen: boolean
  assistantTurns: AssistantTurn[]
  assistantDraft: string
  assistantMode: 'local' | 'cloud'
  assistantConsentOpen: boolean
  assistantConsentAccepted: boolean
  assistantConsentResumeDock: boolean
  assistantIncludeDocuments: boolean
}

export type StoreAction =
  | { type: 'hydrate-route'; route: RouteState }
  | { type: 'scenarios'; value: ScenarioDefinition[] }
  | { type: 'run-start' }
  | { type: 'run-success'; value: TwinRunPayload }
  | { type: 'run-error'; value: string }
  | { type: 'engine'; value: TurbineState['engineStatus'] }
  | { type: 'theme'; value: ThemePreference }
  | { type: 'seed-draft'; value: string }
  | { type: 'seed-commit'; value: number }
  | { type: 'scenario'; value: string }
  | { type: 'sample'; value: number }
  | { type: 'component'; value: ComponentId }
  | { type: 'navigate'; value: Pick<RouteState, 'page' | 'componentId'> }
  | { type: 'assistant-open'; value: boolean }
  | { type: 'assistant-mode'; value: 'local' | 'cloud' }
  | { type: 'assistant-consent-open'; value: { open: boolean; resumeDock: boolean } }
  | { type: 'assistant-consent-accepted'; value: boolean }
  | { type: 'assistant-documents'; value: boolean }
  | { type: 'assistant-draft'; value: string }
  | { type: 'assistant-turn-add'; value: AssistantTurn }
  | { type: 'assistant-turn-patch'; value: { id: number; patch: Partial<AssistantTurn> } }

export interface StoreValue {
  state: TurbineState
  dispatch: Dispatch<StoreAction>
  navigate: (page: RouteState['page'], componentId?: ComponentId) => void
  changeScenario: (scenarioId: string) => void
  commitSeed: (value: string) => boolean
  selectSample: (index: number) => void
  selectComponent: (id: ComponentId) => void
  changeTheme: (theme: ThemePreference) => void
  retry: () => void
}

export const StoreContext = createContext<StoreValue | null>(null)
