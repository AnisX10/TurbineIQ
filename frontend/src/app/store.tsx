import { useCallback, useEffect, useLayoutEffect, useMemo, useReducer, useRef } from 'react'
import type { ReactNode } from 'react'
import { api } from '../api'
import { DEFAULT_SAMPLE_INDEX, DEFAULT_SCENARIO, parseRoute, routeHash } from './router'
import type { ComponentId, RouteState, ThemePreference } from './router'
import { readThemePreference, writeThemePreference } from './router'
import { StoreContext } from './storeContext'
import type { StoreAction, TurbineState } from './storeContext'

function reducer(state: TurbineState, action: StoreAction): TurbineState {
  switch (action.type) {
    case 'hydrate-route':
      return { ...state, ...action.route, seedInput: String(action.route.seed), requestError: '' }
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
  }
}

function initialState(): TurbineState {
  const route = parseRoute(window.location.hash)
  let theme: ThemePreference = 'system'
  try {
    theme = readThemePreference(window.localStorage)
  } catch {
    theme = 'system'
  }
  return {
    ...route,
    seedInput: String(route.seed),
    run: null,
    scenarios: [],
    theme,
    engineStatus: 'checking',
    loading: true,
    requestError: '',
  }
}

export function TurbineStoreProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, undefined, initialState)
  const stateRef = useRef(state)
  useLayoutEffect(() => { stateRef.current = state }, [state])

  const writeUrl = useCallback((replace: boolean) => {
    const hash = routeHash(stateRef.current)
    if (window.location.hash === hash) return
    if (replace) window.history.replaceState(null, '', hash)
    else window.history.pushState(null, '', hash)
  }, [])

  useEffect(() => {
    const sync = () => dispatch({ type: 'hydrate-route', route: parseRoute(window.location.hash) })
    window.addEventListener('hashchange', sync)
    window.addEventListener('popstate', sync)
    if (!window.location.hash) window.history.replaceState(null, '', routeHash(stateRef.current))
    return () => {
      window.removeEventListener('hashchange', sync)
      window.removeEventListener('popstate', sync)
    }
  }, [])

  useEffect(() => {
    const root = document.documentElement
    if (state.theme === 'system') root.removeAttribute('data-theme')
    else root.dataset.theme = state.theme
    try {
      writeThemePreference(window.localStorage, state.theme)
    } catch {
      return
    }
  }, [state.theme])

  useEffect(() => {
    let active = true
    Promise.all([api.health(), api.scenarios()]).then(([health, scenarios]) => {
      if (!active) return
      dispatch({ type: 'engine', value: health.status === 'ok' ? 'connected' : 'offline' })
      dispatch({ type: 'scenarios', value: scenarios })
    }).catch(() => { if (active) dispatch({ type: 'engine', value: 'offline' }) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (state.scenarios.length === 0 || state.scenarios.some((item) => item.scenario_id === state.scenarioId)) return
    const fallback = state.scenarios.some((item) => item.scenario_id === DEFAULT_SCENARIO)
      ? DEFAULT_SCENARIO
      : state.scenarios[0].scenario_id
    dispatch({ type: 'scenario', value: fallback })
    window.history.replaceState(null, '', routeHash({ ...stateRef.current, scenarioId: fallback }))
  }, [state.scenarios, state.scenarioId])

  useEffect(() => {
    let active = true
    dispatch({ type: 'run-start' })
    api.run(state.scenarioId, state.seed).then((payload) => {
      if (active) dispatch({ type: 'run-success', value: payload })
    }).catch((error: unknown) => {
      if (active) dispatch({ type: 'run-error', value: error instanceof Error ? error.message : 'The synthetic run request returned an error.' })
    })
    return () => { active = false }
  }, [state.scenarioId, state.seed])

  useEffect(() => {
    if (window.location.hash !== routeHash(stateRef.current)) writeUrl(false)
  }, [state.page, state.componentId, state.scenarioId, state.seed, writeUrl])

  useEffect(() => {
    const timer = window.setTimeout(() => writeUrl(true), 160)
    return () => window.clearTimeout(timer)
  }, [state.sampleIndex, writeUrl])

  const navigate = useCallback((page: RouteState['page'], componentId: ComponentId = state.componentId ?? 'compressor') => {
    dispatch({ type: 'navigate', value: { page, componentId: page === 'components' ? componentId : null } })
  }, [state.componentId])
  const changeScenario = useCallback((scenarioId: string) => {
    dispatch({ type: 'scenario', value: scenarioId })
    const next = { ...state, scenarioId, sampleIndex: DEFAULT_SAMPLE_INDEX }
    window.history.pushState(null, '', routeHash(next))
  }, [state])
  const commitSeed = useCallback((value: string) => {
    if (!/^\d+$/.test(value)) return false
    const seed = Number(value)
    if (!Number.isSafeInteger(seed)) return false
    dispatch({ type: 'seed-commit', value: seed })
    window.history.pushState(null, '', routeHash({ ...state, seed, sampleIndex: DEFAULT_SAMPLE_INDEX }))
    return true
  }, [state])
  const selectSample = useCallback((index: number) => dispatch({ type: 'sample', value: index }), [])
  const selectComponent = useCallback((id: ComponentId) => {
    dispatch({ type: 'component', value: id })
    if (state.page === 'components') window.history.pushState(null, '', routeHash({ ...state, componentId: id }))
  }, [state])
  const changeTheme = useCallback((theme: ThemePreference) => dispatch({ type: 'theme', value: theme }), [])
  const retry = useCallback(() => {
    dispatch({ type: 'run-start' })
    api.run(state.scenarioId, state.seed).then((value) => dispatch({ type: 'run-success', value })).catch((error: unknown) => dispatch({ type: 'run-error', value: error instanceof Error ? error.message : 'The synthetic run request returned an error.' }))
  }, [state.scenarioId, state.seed])

  const value = useMemo(() => ({ state, dispatch, navigate, changeScenario, commitSeed, selectSample, selectComponent, changeTheme, retry }), [state, navigate, changeScenario, commitSeed, selectSample, selectComponent, changeTheme, retry])
  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>
}
