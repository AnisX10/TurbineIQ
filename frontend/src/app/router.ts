export const COMPONENT_IDS = ['inlet', 'compressor', 'combustor', 'turbine', 'shaft', 'generator'] as const
export type ComponentId = typeof COMPONENT_IDS[number]
export type RoutePage = 'overview' | 'components' | 'evidence' | 'assistant'
export type ThemePreference = 'system' | 'light' | 'dark'

export interface RouteState {
  page: RoutePage
  componentId: ComponentId | null
  scenarioId: string
  seed: number
  sampleIndex: number
  evidenceQuery?: string
  evidenceTopK?: number
  evidenceCitation?: string
}

export const DEFAULT_SCENARIO = 'compressor_fouling'
export const DEFAULT_SEED = 42
export const DEFAULT_SAMPLE_INDEX = 72
const ROUTE_PAGES = new Set<RoutePage>(['overview', 'components', 'evidence', 'assistant'])

function parseNonNegativeInteger(value: string | null, fallback: number): number {
  if (value === null || !/^\d+$/.test(value)) return fallback
  const parsed = Number(value)
  return Number.isSafeInteger(parsed) ? parsed : fallback
}

export function parseRoute(hash: string): RouteState {
  const [rawPath, rawQuery = ''] = hash.replace(/^#/, '').split('?')
  const path = rawPath.replace(/^\/+|\/+$/g, '')
  const segments = path ? path.split('/') : []
  const params = new URLSearchParams(rawQuery)
  const seed = parseNonNegativeInteger(params.get('seed'), DEFAULT_SEED)
  const rawSampleIndex = parseNonNegativeInteger(params.get('i'), DEFAULT_SAMPLE_INDEX)
  const sampleIndex = rawSampleIndex < 96 ? rawSampleIndex : DEFAULT_SAMPLE_INDEX
  const scenarioId = params.get('scenario')?.trim() || DEFAULT_SCENARIO
  const rawEvidenceQuery = params.get('q')?.trim() ?? ''
  const evidenceQuery = rawEvidenceQuery.length <= 300 ? rawEvidenceQuery : ''
  const rawTopK = parseNonNegativeInteger(params.get('top_k'), 4)
  const evidenceTopK = rawTopK >= 1 && rawTopK <= 8 ? rawTopK : 4
  const rawCitation = params.get('cite')?.trim() ?? ''
  const evidenceCitation = rawCitation.length <= 180 ? rawCitation : ''
  const shared = {
    scenarioId,
    seed,
    sampleIndex,
    evidenceQuery,
    evidenceTopK,
    ...(evidenceCitation ? { evidenceCitation } : {}),
  }

  if (segments[0] === 'components') {
    const componentId = segments[1]
    if (segments.length === 2 && COMPONENT_IDS.includes(componentId as ComponentId)) {
      return { page: 'components', componentId: componentId as ComponentId, ...shared }
    }
    return { page: 'overview', componentId: 'compressor', ...shared }
  }

  const page = segments[0] as RoutePage
  if (segments.length === 1 && ROUTE_PAGES.has(page)) {
    const rawComponent = params.get('component')
    const componentId = COMPONENT_IDS.includes(rawComponent as ComponentId) ? rawComponent as ComponentId : 'compressor'
    return { page, componentId, ...shared }
  }
  return { page: 'overview', componentId: 'compressor', ...shared }
}

export function routeHash(state: Pick<RouteState, 'page' | 'componentId' | 'scenarioId' | 'seed' | 'sampleIndex'> & Partial<Pick<RouteState, 'evidenceQuery' | 'evidenceTopK' | 'evidenceCitation'>>): string {
  const path = state.page === 'components'
    ? `components/${state.componentId && COMPONENT_IDS.includes(state.componentId) ? state.componentId : 'compressor'}`
    : state.page
  const params = new URLSearchParams({ scenario: state.scenarioId, seed: String(state.seed), i: String(state.sampleIndex) })
  if (state.page === 'evidence' || state.evidenceQuery || (state.evidenceTopK !== undefined && state.evidenceTopK !== 4)) {
    params.set('q', state.evidenceQuery ?? '')
    params.set('top_k', String(state.evidenceTopK ?? 4))
    if (state.evidenceCitation) params.set('cite', state.evidenceCitation)
  }
  if (state.page !== 'components' && state.componentId) params.set('component', state.componentId)
  return `#/${path}?${params.toString()}`
}

export function readThemePreference(storage: Pick<Storage, 'getItem'> | null | undefined): ThemePreference {
  try {
    const saved = storage?.getItem('turbineiq-theme')
    return saved === 'light' || saved === 'dark' ? saved : 'system'
  } catch {
    return 'system'
  }
}

export function writeThemePreference(storage: Pick<Storage, 'setItem'> | null | undefined, theme: ThemePreference): void {
  try {
    storage?.setItem('turbineiq-theme', theme)
  } catch {
    return
  }
}
