import { describe, expect, it } from 'vitest'
import { turbineReducer } from './reducer'
import type { TurbineState } from './storeContext'

const state: TurbineState = {
  page: 'overview', componentId: 'compressor', scenarioId: 'compressor_fouling', seed: 42,
  sampleIndex: 72, evidenceQuery: '', evidenceTopK: 4, seedInput: '42', run: null, scenarios: [],
  theme: 'system', engineStatus: 'checking', loading: false, requestError: '', assistantOpen: false,
  assistantTurns: [], assistantDraft: '', assistantMode: 'local', assistantConsentOpen: false,
  assistantConsentAccepted: false, assistantConsentResumeDock: false, assistantIncludeDocuments: false,
}

describe('assistant conversation store', () => {
  it('shares the conversation across route navigation and patches streaming turns', () => {
    const turn = {
      id: 1, question: 'Explain the selected residual.',
      context: { scenarioId: 'compressor_fouling', scenarioName: 'Compressor-performance drift', seed: 42, sampleIndex: 72, componentId: 'compressor' as const, componentName: 'Compressor' },
      partialAnswer: '', streaming: true,
    }
    const withTurn = turbineReducer(state, { type: 'assistant-turn-add', value: turn })
    const onEvidence = turbineReducer(withTurn, { type: 'navigate', value: { page: 'evidence', componentId: 'compressor' } })
    const streamed = turbineReducer(onEvidence, { type: 'assistant-turn-patch', value: { id: 1, patch: { partialAnswer: 'Current output is' } } })
    expect(streamed.page).toBe('evidence')
    expect(streamed.assistantTurns[0].partialAnswer).toBe('Current output is')
    expect(streamed.assistantTurns[0].context.seed).toBe(42)
  })

  it('keeps cloud consent and dock state independent from route changes', () => {
    const open = turbineReducer(state, { type: 'assistant-open', value: true })
    const consent = turbineReducer(open, { type: 'assistant-consent-open', value: { open: true, resumeDock: true } })
    const confirmed = turbineReducer(consent, { type: 'assistant-consent-accepted', value: true })
    const routed = turbineReducer(confirmed, { type: 'navigate', value: { page: 'components', componentId: 'turbine' } })
    expect(routed.assistantOpen).toBe(true)
    expect(routed.assistantConsentAccepted).toBe(true)
    expect(routed.assistantMode).toBe('cloud')
  })
})
