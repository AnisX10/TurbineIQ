import { lazy, Suspense, useState } from 'react'
import { BoundarySheet, IconRail, MobileBottomBar, PageHeader } from './Shell'
import { TurbineStoreProvider } from './app/store'
import { useTurbineStore } from './app/useTurbineStore'
import { getBoundaryDetails } from './shellLogic'
import Overview from './features/overview/Overview'
import './Shell.css'

const ComponentDetail = lazy(() => import('./features/component-detail/ComponentDetail'))
const Evidence = lazy(() => import('./features/evidence/Evidence'))
const Assistant = lazy(() => import('./features/assistant/Assistant'))

function RouteLoadingState({ label }: { label: string }) {
  return <section className="route-loading" aria-label={`Loading ${label}`} aria-busy="true">
    <div className="route-loading-title" />
    <div className="route-loading-panel" />
    <div className="route-loading-panel route-loading-panel-short" />
  </section>
}

function RouteOutlet() {
  const { state } = useTurbineStore()
  if (state.page === 'components') return <Suspense fallback={<RouteLoadingState label="component detail" />}><ComponentDetail /></Suspense>
  if (state.page === 'evidence') return <Suspense fallback={<RouteLoadingState label="Evidence" />}><Evidence /></Suspense>
  if (state.page === 'assistant') return <Suspense fallback={<RouteLoadingState label="Assistant" />}><Assistant /></Suspense>
  return <Overview />
}

function AppShell() {
  const { state, changeTheme } = useTurbineStore()
  const [boundaryOpen, setBoundaryOpen] = useState(false)
  const snapshot = state.run?.snapshots[state.sampleIndex] ?? null
  const scenario = state.scenarios.find((item) => item.scenario_id === state.scenarioId)
  const boundary = getBoundaryDetails({ run: state.run, snapshot, scenario, scenarioId: state.scenarioId })
  const selectedComponentId = state.componentId ?? 'compressor'

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content" onClick={(event) => { event.preventDefault(); document.getElementById('main-content')?.focus() }}>Skip to content</a>
      <IconRail page={state.page} selectedComponentId={selectedComponentId} engineStatus={state.engineStatus} theme={state.theme} onThemeChange={changeTheme} boundaryOpen={boundaryOpen} onBoundary={() => setBoundaryOpen(true)} />
      <main id="main-content" className="main-area" tabIndex={-1} aria-label="TurbineIQ workspace">
        <PageHeader page={state.page} seed={String(state.seed)} engineStatus={state.engineStatus} theme={state.theme} onThemeChange={changeTheme} boundaryOpen={boundaryOpen} onBoundary={() => setBoundaryOpen(true)} />
        <RouteOutlet />
      </main>
      <MobileBottomBar page={state.page} selectedComponentId={selectedComponentId} />
      <BoundarySheet open={boundaryOpen} onClose={() => setBoundaryOpen(false)} seed={String(state.seed)} scenario={boundary.scenario} modelName={boundary.modelName} provenance={boundary.provenance} />
    </div>
  )
}

export default function App() {
  return <TurbineStoreProvider><AppShell /></TurbineStoreProvider>
}
