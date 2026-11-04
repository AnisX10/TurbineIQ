import { useState } from 'react'
import type { KeyboardEvent } from 'react'
import { useTurbineStore } from '../../app/useTurbineStore'
import type { TwinComponentState, TwinMetric } from '../../types'
import { metricNumber, numberText, signedNumber } from '../../lib/format'
import { ValueWithUnit } from '../../lib/ValueWithUnit'
import { ENGINE_START_COMMAND } from '../../lib/engine'
import { presentMetric } from '../overview/metricFormatting'
import { ReferenceMetric } from '../overview/metricPresentation'
import { PublishedReferenceBlock } from '../overview/PublishedReference'
import { ReplayTimeline } from '../overview/ReplayTimeline'
import { TimelineChart } from '../overview/TimelineChart'
import type { ChartSeries } from '../overview/TimelineChart'
import { EvidencePanel } from '../evidence/EvidencePanel'
import './ComponentDetail.css'

type DetailTab = 'metrics' | 'over-time' | 'evidence'
const DETAIL_TABS: Array<{ id: DetailTab; label: string }> = [
  { id: 'metrics', label: 'Metrics' },
  { id: 'over-time', label: 'Over time' },
  { id: 'evidence', label: 'Evidence' },
]

function MetricValue({ metric }: { metric: TwinMetric }) {
  const value = presentMetric(metric)
  return <ValueWithUnit value={value.value} unit={value.unit} />
}

function MetricLedger({ component }: { component: TwinComponentState }) {
  return (
    <div className="metric-ledger-wrap">
      <table className="metric-ledger">
        <thead><tr><th>Metric</th><th>Synthetic</th><th>Reference</th><th>Delta</th><th>Provenance</th></tr></thead>
        <tbody>{component.metrics.map((metric) => {
          const presented = presentMetric(metric)
          const current = metricNumber(metric.value, metric.key, metric.unit)
          const reference = metric.reference_value === null ? null : metricNumber(metric.reference_value, metric.key, metric.unit)
          const delta = current === null || reference === null ? null : current - reference
          const digits = presented.unit === 'K' ? 1 : 2
          return <tr key={metric.key}>
            <th scope="row">{metric.label}</th>
            <td><MetricValue metric={metric} /></td>
            <td><ValueWithUnit value={reference === null ? '—' : numberText(reference, digits)} unit={presented.unit} /></td>
            <td className={delta === 0 ? 'zero-value' : ''}><ValueWithUnit value={delta === null ? '—' : signedNumber(delta, digits)} unit={presented.unit} /></td>
            <td className="metric-provenance-cell">{presented.provenance}<ReferenceMetric metric={metric} /></td>
          </tr>
        })}</tbody>
      </table>
    </div>
  )
}

function TopMetrics({ metrics }: { metrics: TwinMetric[] }) {
  return <section className="detail-kpis" aria-label="Top component metrics">{metrics.slice(0, 3).map((metric) => {
    const value = presentMetric(metric)
    return <article className="detail-kpi" key={metric.key}><span className="detail-kpi-label">{metric.label}</span><strong><ValueWithUnit value={value.value} unit={value.unit} /></strong><span className="detail-kpi-note">{value.provenance}</span></article>
  })}</section>
}

function LoadingState() {
  return <div className="component-detail-loading" aria-label="Loading component metrics"><div /><div /><div /><div /></div>
}

export default function ComponentDetail() {
  const { state, selectSample, retry } = useTurbineStore()
  const [activeTab, setActiveTab] = useState<DetailTab>('metrics')
  const [playing, setPlaying] = useState(false)
  const componentId = state.componentId ?? 'compressor'
  const snapshot = state.run?.snapshots[state.sampleIndex]
  const component = snapshot?.components.find((item) => item.component_id === componentId)
  const componentName = component?.label ?? componentId
  const tabIndex = DETAIL_TABS.findIndex((tab) => tab.id === activeTab)

  const onTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const move = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : event.key === 'Home' ? -tabIndex : event.key === 'End' ? DETAIL_TABS.length - 1 - tabIndex : 0
    if (!move) return
    event.preventDefault()
    const nextIndex = (tabIndex + move + DETAIL_TABS.length) % DETAIL_TABS.length
    setActiveTab(DETAIL_TABS[nextIndex].id)
    document.getElementById(`detail-tab-${DETAIL_TABS[nextIndex].id}`)?.focus()
  }

  if (!state.run || !snapshot || !component) {
    return <div className="component-detail-page" id="route-outlet"><div className="detail-breadcrumb"><a href="#/overview">Overview</a><span aria-hidden="true">/</span><span>{componentName}</span><span className="neutral-status">Synthetic</span></div>{state.engineStatus === 'offline' ? <div className="engine-banner" role="alert"><strong>Local engine offline.</strong><span>Start it with</span><code>{ENGINE_START_COMMAND}</code></div> : state.requestError ? <div className="request-banner" role="alert"><span>{state.requestError}</span><button type="button" className="button-quiet" onClick={retry}>Retry</button></div> : <LoadingState />}</div>
  }

  const timeline = state.run.timeline
  const selectedMetric = component.metrics.find((metric) => typeof metric.value === 'number')
  const samples = state.run.snapshots
  const values = selectedMetric ? samples.map((item) => {
    const sampleComponent = item.components.find((candidate) => candidate.component_id === componentId)
    const sampleMetric = sampleComponent?.metrics.find((candidate) => candidate.key === selectedMetric.key)
    return sampleMetric ? metricNumber(sampleMetric.value, sampleMetric.key, sampleMetric.unit) : null
  }) : []
  const referenceNumber = selectedMetric?.reference_value === null || !selectedMetric ? null : metricNumber(selectedMetric.reference_value, selectedMetric.key, selectedMetric.unit)
  const displayUnit = selectedMetric ? presentMetric(selectedMetric).unit ?? '' : ''
  const observations = values.map((value) => value)
  const references = values.map(() => referenceNumber)
  const residuals = values.map((value) => value === null || referenceNumber === null ? null : value - referenceNumber)
  const hasSeries = values.some((value) => value !== null)
  const hasResiduals = residuals.some((value) => value !== null)
  const metricSeries: ChartSeries[] = [
    ...(referenceNumber === null ? [] : [{ key: 'reference-model', label: 'Reference model', values: references, style: 'reference' as const }]),
    { key: 'synthetic-observation', label: 'Synthetic observation', values: observations, style: 'observation' },
  ]
  const residualSeries: ChartSeries[] = [{ key: 'residual', label: 'Residual', values: residuals, style: 'residual' }]
  const showPublished = componentId === 'turbine' || componentId === 'generator'

  return (
    <div className="component-detail-page" id="route-outlet">
      <div className="detail-breadcrumb"><a href={`#/overview?scenario=${encodeURIComponent(state.scenarioId)}&seed=${state.seed}&i=${state.sampleIndex}`}>Overview</a><span aria-hidden="true">/</span><h2>{component.label}</h2><span className="neutral-status">Synthetic</span></div>
      <div className="detail-tabs" role="tablist" aria-label={`${component.label} details`}>
        {DETAIL_TABS.map((tab) => <button key={tab.id} id={`detail-tab-${tab.id}`} type="button" role="tab" aria-selected={activeTab === tab.id} aria-controls="detail-tabpanel" tabIndex={activeTab === tab.id ? 0 : -1} onClick={() => setActiveTab(tab.id)} onKeyDown={onTabKeyDown}>{tab.label}</button>)}
      </div>
      <div id="detail-tabpanel" className="detail-tabpanel" role="tabpanel" aria-labelledby={`detail-tab-${activeTab}`} tabIndex={0}>
        {activeTab === 'metrics' && <>
          <p className="component-summary">{component.summary}</p>
          <TopMetrics metrics={component.metrics} />
          <section className="detail-panel panel" aria-labelledby="metric-ledger-title"><div className="detail-panel-heading"><h3 id="metric-ledger-title">Metric ledger</h3><span>Sample {state.sampleIndex + 1} · {snapshot.timestamp_utc}</span></div><MetricLedger component={component} /></section>
          {showPublished && <PublishedReferenceBlock />}
        </>}
        {activeTab === 'over-time' && <ReplayTimeline timeline={timeline} selectedIndex={state.sampleIndex} isPlaying={playing} setPlaying={setPlaying} onSelect={(index) => { setPlaying(false); selectSample(index) }} title={`${component.label} over time`} description="Select a sample to compare the synthetic observation with its fixed reference.">
          <div className="component-trends">
            <section className="detail-panel panel" aria-labelledby="metric-trend-title"><div className="detail-panel-heading"><h3 id="metric-trend-title">{selectedMetric?.label ?? 'Component metric'}</h3><span>{displayUnit || 'Unit not supplied'}</span></div>{hasSeries ? <TimelineChart timeline={timeline} selectedIndex={state.sampleIndex} onSelect={(index) => { setPlaying(false); selectSample(index) }} series={metricSeries} unit={displayUnit} residualValues={residuals} /> : <p className="timeline-empty">No per-sample series is available in the run payload for {component.label}.</p>}</section>
            <section className="detail-panel panel" aria-labelledby="residual-trend-title"><div className="detail-panel-heading"><h3 id="residual-trend-title">Residual over time</h3><span>{displayUnit || 'Unit not supplied'}</span></div>{hasResiduals ? <TimelineChart timeline={timeline} selectedIndex={state.sampleIndex} onSelect={(index) => { setPlaying(false); selectSample(index) }} series={residualSeries} unit={displayUnit} zeroBaseline /> : <p className="timeline-empty">No reference value is available for {selectedMetric?.label ?? component.label}; residual series cannot be calculated from the payload.</p>}</section>
          </div>
        </ReplayTimeline>}
        {activeTab === 'evidence' && <EvidencePanel initialQuery={component.label} />}
      </div>
    </div>
  )
}
