import { DEFAULT_SAMPLE_INDEX } from './router'
import type { StoreAction, TurbineState } from './storeContext'

export function turbineReducer(state: TurbineState, action: StoreAction): TurbineState {
  switch (action.type) {
    case 'hydrate-route':
      return { ...state, ...action.route, evidenceCitation: action.route.evidenceCitation, seedInput: String(action.route.seed), requestError: '' }
    case 'scenarios':
      return { ...state, scenarios: action.value }
    case 'run-start':
      return { ...state, loading: true, requestError: '' }
    case 'run-success':
      return { ...state, run: action.value, loading: false, requestError: '', sampleIndex: state.sampleIndex < action.value.run.sample_count ? state.sampleIndex : Math.min(DEFAULT_SAMPLE_INDEX, action.value.run.sample_count - 1) }
    case 'run-error':
      return { ...state, loading: false, requestError: action.value }
    case 'engine':
      return { ...state, engineStatus: action.value }
    case 'theme':
      return { ...state, theme: action.value }
    case 'seed-draft':
      return { ...state, seedInput: action.value }
    case 'seed-commit':
      return { ...state, seed: action.value, seedInput: String(action.value), sampleIndex: DEFAULT_SAMPLE_INDEX, requestError: '' }
    case 'scenario':
      return { ...state, scenarioId: action.value, sampleIndex: DEFAULT_SAMPLE_INDEX, requestError: '' }
    case 'sample':
      return { ...state, sampleIndex: Math.max(0, Math.min(action.value, (state.run?.run.sample_count ?? 96) - 1)) }
    case 'component':
      return { ...state, componentId: action.value }
    case 'navigate':
      return { ...state, ...action.value }
    case 'assistant-open':
      return { ...state, assistantOpen: action.value }
    case 'assistant-mode':
      return { ...state, assistantMode: action.value }
    case 'assistant-consent-open':
      return { ...state, assistantConsentOpen: action.value.open, assistantConsentResumeDock: action.value.resumeDock }
    case 'assistant-consent-accepted':
      return { ...state, assistantConsentAccepted: action.value, assistantMode: action.value ? 'cloud' : 'local' }
    case 'assistant-documents':
      return { ...state, assistantIncludeDocuments: action.value }
    case 'assistant-draft':
      return { ...state, assistantDraft: action.value }
    case 'assistant-turn-add':
      return { ...state, assistantTurns: [...state.assistantTurns, action.value] }
    case 'assistant-turn-patch':
      return {
        ...state,
        assistantTurns: state.assistantTurns.map((turn) => turn.id === action.value.id
          ? { ...turn, ...action.value.patch }
          : turn),
      }
  }
}
