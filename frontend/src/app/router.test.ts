import { describe, expect, it } from 'vitest'
import { parseRoute, routeHash } from './router'

describe('URL state', () => {
  it('round trips route and shared query state', () => {
    const route = { page: 'components' as const, componentId: 'compressor' as const, scenarioId: 'compressor_fouling', seed: 42, sampleIndex: 72, evidenceQuery: '', evidenceTopK: 4 }
    expect(parseRoute(routeHash(route))).toEqual(route)
  })

  it('keeps the selected component on overview routes', () => {
    const route = { page: 'overview' as const, componentId: 'turbine' as const, scenarioId: 'compressor_fouling', seed: 7, sampleIndex: 12, evidenceQuery: '', evidenceTopK: 4 }
    expect(parseRoute(routeHash(route))).toEqual(route)
  })

  it('defaults malformed, negative, and out-of-range values without throwing', () => {
    expect(parseRoute('#/overview?scenario=&seed=-5&i=999')).toMatchObject({
      page: 'overview', scenarioId: 'compressor_fouling', seed: 42, sampleIndex: 72,
    })
    expect(parseRoute('#/overview?seed=not-a-number&i=2.5')).toMatchObject({ seed: 42, sampleIndex: 72 })
    expect(parseRoute('#/overview?seed=9007199254740992')).toMatchObject({ seed: 42 })
  })

  it('round trips evidence query and result count and defaults invalid values', () => {
    const route = { page: 'evidence' as const, componentId: 'compressor' as const, scenarioId: 'compressor_fouling', seed: 42, sampleIndex: 72, evidenceQuery: 'Brayton cycle', evidenceTopK: 6 }
    expect(parseRoute(routeHash(route))).toEqual(route)
    expect(parseRoute('#/evidence?q=abc&top_k=0')).toMatchObject({ evidenceQuery: 'abc', evidenceTopK: 4 })
    expect(parseRoute(`#/evidence?q=${'x'.repeat(301)}&top_k=99`)).toMatchObject({ evidenceQuery: '', evidenceTopK: 4 })
  })

  it('preserves a bounded citation selection for the Evidence reader', () => {
    const route = { page: 'evidence' as const, componentId: 'compressor' as const, scenarioId: 'compressor_fouling', seed: 42, sampleIndex: 72, evidenceQuery: 'Brayton cycle', evidenceTopK: 4, evidenceCitation: '[Cycle note, § 3]' }
    expect(parseRoute(routeHash(route))).toEqual(route)
    expect(parseRoute(`#/evidence?cite=${'x'.repeat(181)}`)).not.toHaveProperty('evidenceCitation')
  })
})

describe('route validation', () => {
  it('accepts only the six existing component identifiers', () => {
    for (const id of ['inlet', 'compressor', 'combustor', 'turbine', 'shaft', 'generator']) {
      expect(parseRoute(`#/components/${id}`).componentId).toBe(id)
    }
    expect(parseRoute('#/components/unknown')).toMatchObject({ page: 'overview', componentId: 'compressor' })
    expect(parseRoute('#/components/compressor/extra').page).toBe('overview')
  })

  it('redirects unknown routes to overview while preserving valid URL state', () => {
    expect(parseRoute('#/not-a-route?scenario=compressor_fouling&seed=3&i=4')).toMatchObject({
      page: 'overview', scenarioId: 'compressor_fouling', seed: 3, sampleIndex: 4,
    })
  })
})
