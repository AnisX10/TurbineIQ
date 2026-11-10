import { createContext } from 'react'
import type { Dispatch } from 'react'
import type { ComponentId, RouteState, ThemePreference } from './router'
import type { ScenarioDefinition, TwinRunPayload } from '../types'

export interface TurbineState extends RouteState {
  seedInput: string
  run: TwinRunPayload | null
  scenarios: ScenarioDefinition[]
  theme: ThemePreference
  engineStatus: 'checking' | 'connected' | 'offline'
  loading: boolean
  requestError: string
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
