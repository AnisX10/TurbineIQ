import { useState } from 'react'
import { BoundarySheet, IconRail, MobileBottomBar, PageHeader } from './Shell'
import { TurbineStoreProvider } from './app/store'
import { useTurbineStore } from './app/useTurbineStore'
import { getBoundaryDetails } from './shellLogic'
import Overview from './features/overview/Overview'
import ComponentDetail from './features/component-detail/ComponentDetail'
import Evidence from './features/evidence/Evidence'
import Assistant from './features/assistant/Assistant'
import './Shell.css'

function RouteOutlet() {
  const { state } = useTurbineStore()
  if (state.page === 'components') return <ComponentDetail />
  if (state.page === 'evidence') return <Evidence />
  if (state.page === 'assistant') return <Assistant />
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
