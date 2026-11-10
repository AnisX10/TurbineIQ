import { describe, expect, it } from 'vitest'
import { generateAssistantSuggestions } from './suggestions'

describe('generateAssistantSuggestions', () => {
  it('creates stable questions from the selected synthetic context', () => {
    const context = { flaggedSamples: 0, sampleNumber: 73, componentName: 'Compressor', residualKw: -1627.5 }
    expect(generateAssistantSuggestions(context)).toEqual([
      'Why was sample 73 not flagged by the local residual screen?',
      'Explain the Compressor metrics at sample 73.',
      'What does the -1627.5 kW residual mean?',
    ])
    expect(generateAssistantSuggestions(context)).toEqual(generateAssistantSuggestions(context))
  })

  it('includes flagged sample count and handles missing residuals honestly', () => {
    expect(generateAssistantSuggestions({ flaggedSamples: 4, sampleNumber: 5, componentName: 'Turbine', residualKw: null })).toEqual([
      'What distinguishes the 4 flagged samples in this run?',
      'Explain the Turbine metrics at sample 5.',
      'How should I interpret the current sample residual?',
    ])
  })
})
