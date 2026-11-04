import { useState } from 'react'
import type { ComponentId } from '../../app/router'
import { useTurbineStore } from '../../app/useTurbineStore'
import { FilterRow } from './FilterRow'
import { KpiRow } from './KpiRow'
import { StationLedger } from './StationLedger'
import { ComponentLedger } from './ComponentLedger'
import { ReplayTimeline } from './ReplayTimeline'
import { StageCard } from './StageCard'
import './Overview.css'

function RunState() {
  const { state, retry } = useTurbineStore()
  if (state.engineStatus === 'offline') return <div className="engine-banner" role="alert"><strong>Local engine offline.</strong> Start it with <code>.\\.venv\\Scripts\\python.exe -m uvicorn turbineiq.api.main:app --host 127.0.0.1 --port 8000</code> and retry the request.</div>
  if (state.requestError) return <div className="request-banner" role="alert"><span>The run request returned an error: {state.requestError}</span><button className="button button-quiet" type="button" onClick={retry}>Retry</button></div>
  return null
}

function FilterSkeleton() {
  return <div className="overview-filter-skeleton" aria-hidden="true"><div className="skeleton-line" /></div>
}

function KpiSkeleton() {
  return <div className="skeleton-kpis" aria-hidden="true"><i /><i /><i /><i /></div>
}

function StationSkeleton() {
  return <section className="station-ledger panel station-ledger-skeleton" aria-label="Loading station measurements"><div className="card-heading"><h2>Station ledger</h2></div>{[1, 2, 3, 4].map((station) => <div className="station-skeleton-row" key={station}><span>Station {station}</span><i /><i /><i /></div>)}</section>
}

function ComponentLedgerSkeleton() {
  return <section className="component-ledger panel component-ledger-skeleton" aria-label="Loading component measurements" aria-busy="true"><div className="card-heading"><h2>Component ledger</h2><span>6 components</span></div>{[1, 2, 3, 4, 5, 6].map((row) => <div className="component-skeleton-row" key={row} aria-hidden="true"><i /><i /><i /></div>)}<div className="component-metrics-skeleton" aria-hidden="true"><i className="skeleton-metric-heading" />{[1, 2, 3, 4].map((row) => <div className="component-metric-skeleton-row" key={row}><i /><i /><i /></div>)}</div><div className="mesh-picker-slot" /><div className="published-reference-skeleton" aria-hidden="true"><i className="skeleton-reference-heading" />{[1, 2, 3, 4].map((row) => <div key={row}><i /><i /></div>)}<i className="skeleton-reference-note" /></div><div className="component-detail-link-skeleton" /></section>
}

function TimelineSkeleton() {
  return <section className="timeline-card panel timeline-skeleton" aria-label="Loading synthetic timeline" aria-busy="true"><div className="timeline-heading"><div><h2>Electrical output over 24 hours</h2><p>Where does the observation depart from the reference?</p></div><span className="skeleton-timeline-control" aria-hidden="true" /></div><div className="skeleton-chart" aria-hidden="true" /><div className="skeleton-timeline-scrubber" aria-hidden="true" /><div className="skeleton-timeline-button" aria-hidden="true" /></section>
}

export default function Overview() {
  const { state, selectSample, selectComponent } = useTurbineStore()
  const [isPlaying, setPlaying] = useState(false)
  const [hoveredComponent, setHoveredComponent] = useState<ComponentId | null>(null)
  const run = state.run
  const snapshot = run?.snapshots[state.sampleIndex] ?? run?.snapshot
  const timelineRow = run?.timeline[state.sampleIndex]
  const selectedId = state.componentId ?? 'compressor'
  const viewSelectedId = hoveredComponent ?? selectedId
  const selectKnownComponent = (id: string) => {
    if (['inlet', 'compressor', 'combustor', 'turbine', 'shaft', 'generator'].includes(id)) selectComponent(id as ComponentId)
  }
  return (
    <div className="overview-page" id="route-outlet" aria-busy={!snapshot || state.loading}>
      <RunState />
      {snapshot ? <FilterRow sample={snapshot} stopPlayback={() => setPlaying(false)} /> : <FilterSkeleton />}
      {snapshot && run ? <KpiRow snapshot={snapshot} timeline={run.timeline} /> : <KpiSkeleton />}
      {state.requestError && run && <p className="stale-run-note">The previous successful run remains visible until a new request succeeds.</p>}
      <div className="overview-band">
        <div className="stage-column">
          <StageCard components={snapshot?.components ?? []} selectedComponentId={viewSelectedId} onSelectComponent={selectKnownComponent} active={Boolean(snapshot)} />
          {snapshot && timelineRow ? <StationLedger snapshot={snapshot} timelineRow={timelineRow} selectedComponentId={selectedId} hoveredComponent={hoveredComponent} onSelect={selectComponent} onHover={setHoveredComponent} /> : <StationSkeleton />}
        </div>
        {snapshot ? <ComponentLedger snapshot={snapshot} selectedId={selectedId} onSelect={selectComponent} /> : <ComponentLedgerSkeleton />}
      </div>
      {run ? <ReplayTimeline timeline={run.timeline} selectedIndex={state.sampleIndex} isPlaying={isPlaying} setPlaying={setPlaying} onSelect={selectSample} /> : <TimelineSkeleton />}
      <span className="sr-only">{hoveredComponent ? `Highlighting ${hoveredComponent} on the Stage.` : ''}</span>
      <span className="sr-only">{run ? `Scenario ${run.run.scenario_name}, seed ${run.run.seed}, sample ${state.sampleIndex + 1}.` : 'Loading synthetic run.'}</span>
      {state.loading && <span className="run-refresh-status" role="status">A new synthetic run is being prepared.</span>}
    </div>
  )
}
