import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { ArrowDown, ArrowUp, CircleHelp, Minus, Pause, Play } from 'lucide-react'
import { useTurbineStore } from '../../app/useTurbineStore'
import type { ComponentId } from '../../app/router'
import type { TimelinePoint, TwinComponentState, TwinMetric, TwinSnapshot } from '../../types'
import { PUBLISHED_6B03_REFERENCE } from '../../lib/publishedReference'
import { formatUtcTime, numberText, powerMw, signedNumber } from '../../lib/format'
import { ValueWithUnit } from '../../lib/ValueWithUnit'
import { setPartPickerHost } from './partPickerHost'
import './Overview.css'

const TurbineViewer = lazy(() => import('../../TurbineViewer').then((module) => ({ default: module.TurbineViewer })))

function metricValue(metric: TwinMetric): string {
  if (typeof metric.value === 'boolean') return metric.value ? 'Yes' : 'No'
  if (metric.key.includes('efficiency')) return (metric.value * 100).toFixed(1)
  return numberText(metric.value, 2)
}

function ReferenceMetric({ metric }: { metric: TwinMetric }) {
  if (metric.reference_value === null) return null
  const isEfficiency = metric.key.includes('efficiency')
  return <span className="metric-provenance">Reference <ValueWithUnit value={isEfficiency ? (metric.reference_value * 100).toFixed(1) : metric.reference_value.toFixed(2)} unit={isEfficiency ? '%' : metric.unit} /></span>
}

function FilterRow({ sample, stopPlayback }: { sample: TwinSnapshot | null; stopPlayback: () => void }) {
  const { state, changeScenario, dispatch, commitSeed } = useTurbineStore()
  const parsedSeed = /^\d+$/.test(state.seedInput) && Number.isSafeInteger(Number(state.seedInput))
  const selected = sample ?? state.run?.snapshots[state.sampleIndex] ?? null
  const sampleCount = state.run?.run.sample_count ?? 96
  const time = selected ? new Date(selected.timestamp_utc).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' }) : '--:--'
  const commit = () => { if (parsedSeed && Number(state.seedInput) !== state.seed) { stopPlayback(); commitSeed(state.seedInput) } }
  return (
    <form className="filter-row" aria-label="Synthetic run filters" onSubmit={(event) => { event.preventDefault(); commit() }}>
      <label className="filter-group filter-scenario">
        <span className="filter-label">Scenario</span>
        <select aria-label="Scenario" value={state.scenarioId} onChange={(event) => { stopPlayback(); changeScenario(event.target.value) }}>
          {state.scenarios.map((scenario) => <option key={scenario.scenario_id} value={scenario.scenario_id}>{scenario.name}</option>)}
          {state.scenarios.length === 0 && <option value={state.scenarioId}>{state.run?.run.scenario_name ?? state.scenarioId}</option>}
        </select>
      </label>
      <label className={`filter-group filter-seed ${!parsedSeed ? 'has-error' : ''}`}>
        <span className="filter-label">Seed</span>
        <input aria-label="Seed" aria-invalid={!parsedSeed} value={state.seedInput} inputMode="numeric" onChange={(event) => dispatch({ type: 'seed-draft', value: event.target.value })} onBlur={commit} />
        {!parsedSeed && <span className="filter-error" role="alert">Enter a non-negative whole number.</span>}
      </label>
      <div className="filter-group filter-sample" aria-label="Selected sample">
        <span className="filter-label">Sample</span>
        <span className="filter-value">{state.sampleIndex + 1} of {sampleCount} · {time} UTC</span>
      </div>
      <div className="filter-group filter-interval">
        <span className="filter-label">Interval</span>
        <span className="filter-value">{state.run?.run.sample_interval_minutes ?? 15} min</span>
      </div>
      {state.loading && state.run && <span className="filter-status" role="status">Updating run; previous sample remains visible.</span>}
    </form>
  )
}

function KpiRow({ snapshot, timeline }: { snapshot: TwinSnapshot; timeline: TimelinePoint[] }) {
  const { state } = useTurbineStore()
  const flagged = timeline.filter((row) => row.anomaly_flag).length
  const residual = snapshot.power_residual_kw / 1000
  const Marker = residual > 0 ? ArrowUp : residual < 0 ? ArrowDown : Minus
  return (
    <section className="kpi-row" aria-label="Selected sample summary">
      <div className="kpi-item"><div className="kpi-label">Reference model</div><div className="kpi-value"><ValueWithUnit value={powerMw(snapshot.model_electrical_power_kw)} unit="MW" /></div><div className="kpi-detail">Simplified model output</div></div>
      <div className="kpi-item"><div className="kpi-label">Synthetic observation</div><div className="kpi-value"><ValueWithUnit value={powerMw(snapshot.synthetic_observed_power_kw)} unit="MW" /></div><div className="kpi-detail">Selected synthetic sample</div></div>
      <div className={`kpi-item kpi-residual ${residual > 0 ? 'is-positive' : residual < 0 ? 'is-negative' : 'is-zero'}`}>
        <div className="kpi-label">Residual</div>
        <div className="kpi-value"><Marker size={16} strokeWidth={1.7} aria-hidden="true" /><ValueWithUnit value={signedNumber(residual)} unit="MW" /></div>
        <div className="kpi-detail">Observation − reference model</div>
      </div>
      <div className="kpi-item"><div className="kpi-label">Flagged samples</div><div className="kpi-value"><ValueWithUnit value={`${flagged} / ${state.run?.run.sample_count ?? timeline.length}`} /></div><div className="kpi-detail">Residual screen</div></div>
    </section>
  )
}

const STATIONS: Array<{ number: number; name: string; component: ComponentId }> = [
  { number: 1, name: 'Inlet', component: 'inlet' },
  { number: 2, name: 'Compressor discharge', component: 'compressor' },
  { number: 3, name: 'Turbine inlet', component: 'combustor' },
  { number: 4, name: 'Exhaust', component: 'turbine' },
]

function stationTemperature(snapshot: TwinSnapshot, row: TimelinePoint | undefined, station: number): { synthetic: number | null; reference: number | null; unit: string } {
  if (station === 1) return { synthetic: snapshot.ambient_temperature_c, reference: null, unit: '°C' }
  if (station === 2) return { synthetic: snapshot.compressor_discharge_temperature_k, reference: snapshot.reference_compressor_discharge_temperature_k, unit: 'K' }
  if (station === 3) {
    const reference = row?.reference_turbine_inlet_temperature_k
    return { synthetic: snapshot.turbine_inlet_temperature_k, reference: typeof reference === 'number' ? reference : null, unit: 'K' }
  }
  return { synthetic: snapshot.exhaust_temperature_k, reference: snapshot.reference_exhaust_temperature_k, unit: 'K' }
}

function StationLedger({ snapshot, timelineRow, selectedComponentId, hoveredComponent, onSelect, onHover }: { snapshot: TwinSnapshot; timelineRow?: TimelinePoint; selectedComponentId: ComponentId; hoveredComponent: ComponentId | null; onSelect: (id: ComponentId) => void; onHover: (id: ComponentId | null) => void }) {
  return (
    <section className="station-ledger panel" aria-labelledby="station-ledger-title">
      <div className="card-heading"><h2 id="station-ledger-title">Station ledger</h2><span>Temperature</span></div>
      <div className="station-list">
        {STATIONS.map((station) => {
          const values = stationTemperature(snapshot, timelineRow, station.number)
          const active = (hoveredComponent ?? selectedComponentId) === station.component
          return (
            <button key={station.number} type="button" className={`station-row ${active ? 'is-selected' : ''}`} onMouseEnter={() => onHover(station.component)} onMouseLeave={() => onHover(null)} onFocus={() => onHover(station.component)} onBlur={() => onHover(null)} onClick={() => onSelect(station.component)}>
              <span className="station-name"><span className="station-number">{station.number}</span><span>{station.name}</span></span>
              <span className="station-observed"><span className="station-kind">Synthetic</span><ValueWithUnit value={values.synthetic === null ? '—' : values.synthetic.toFixed(1)} unit={values.unit} /></span>
              <span className="station-reference"><span className="station-kind">Reference model</span><ValueWithUnit value={values.reference === null ? '—' : values.reference.toFixed(1)} unit={values.unit} /></span>
              {station.number === 1 && <span className="station-pressure"><span className="station-kind">Ambient pressure</span><ValueWithUnit value={snapshot.ambient_pressure_kpa.toFixed(1)} unit="kPa" /></span>}
            </button>
          )
        })}
      </div>
    </section>
  )
}

function ComponentLedger({ snapshot, selectedId, onSelect }: { snapshot: TwinSnapshot; selectedId: ComponentId; onSelect: (id: ComponentId) => void }) {
  const selected = snapshot.components.find((component) => component.component_id === selectedId) ?? snapshot.components[0]
  const knownIds = new Set(['inlet', 'compressor', 'combustor', 'turbine', 'shaft', 'generator'])
  return (
    <section className="component-ledger panel" aria-labelledby="component-ledger-title">
      <div className="card-heading"><h2 id="component-ledger-title">Component ledger</h2><span>{snapshot.components.length} components</span></div>
      <div className="component-rows">
        {snapshot.components.map((component) => {
          const metric = component.metrics[0]
          const id = knownIds.has(component.component_id) ? component.component_id as ComponentId : 'compressor'
          return <button type="button" key={component.component_id} className={`component-row ${id === selectedId ? 'is-selected' : ''}`} aria-pressed={id === selectedId} onClick={() => onSelect(id)}><span className="component-name">{component.label}</span><span className="neutral-status">{component.status_label}</span><span className="component-primary" title={metric ? `${metric.label}: ${metricValue(metric)} ${metric.unit}` : undefined}>{metric ? <ValueWithUnit value={metricValue(metric)} unit={metric.unit} /> : '—'}</span></button>
        })}
      </div>
      {selected && <ComponentMetrics component={selected} />}
      <div className="mesh-picker-slot" id="component-part-picker-slot" ref={setPartPickerHost} />
      <section className="published-reference" aria-labelledby="published-reference-title">
        <h3 id="published-reference-title">Published 6B.03 reference</h3>
        <dl>{PUBLISHED_6B03_REFERENCE.values.map(({ label, value, unit }) => <div key={label}><dt>{label}</dt><dd>{value}{unit && <span className="unit">{unit}</span>}</dd></div>)}</dl>
        <p>{PUBLISHED_6B03_REFERENCE.caveat}</p>
      </section>
      {selected && <a className="component-detail-link" href={`#/components/${selected.component_id}?scenario=${encodeURIComponent(snapshot.scenario_id)}&seed=${snapshot.seed}&i=${snapshot.sample_index}`}>Open component detail</a>}
    </section>
  )
}

function ComponentMetrics({ component }: { component: TwinComponentState }) {
  return (
    <div className="selected-component-metrics">
      <h3>{component.label} metrics</h3>
      {component.metrics.slice(0, 4).map((metric) => <div className="selected-metric" key={metric.key}><span>{metric.label}</span><ValueWithUnit value={metricValue(metric)} unit={typeof metric.value === 'boolean' || metric.key.includes('efficiency') ? undefined : metric.unit} /><span className="metric-provenance">{metric.provenance}</span><ReferenceMetric metric={metric} /></div>)}
    </div>
  )
}

function flagShape(x: number, y: number): string {
  return `M ${x} ${y - 5} L ${x + 5} ${y + 4} L ${x - 5} ${y + 4} Z`
}

function TimelineChart({ timeline, selectedIndex, truthVisible, onSelect, onToggleTruth }: { timeline: TimelinePoint[]; selectedIndex: number; truthVisible: boolean; onSelect: (index: number) => void; onToggleTruth: () => void }) {
  const host = useRef<HTMLDivElement>(null)
  const [measuredWidth, setMeasuredWidth] = useState(800)
  const [table, setTable] = useState(false)
  useEffect(() => {
    if (!host.current) return
    const observer = new ResizeObserver((entries) => setMeasuredWidth(Math.max(320, Math.floor(entries[0]?.contentRect.width ?? 800))))
    observer.observe(host.current)
    return () => observer.disconnect()
  }, [])
  const width = Math.max(measuredWidth, 620)
  const height = 306
  const margin = { top: 20, right: 160, bottom: 36, left: 54 }
  const plotBottom = 214
  const residualTop = 236
  const plotWidth = width - margin.left - margin.right
  const values = timeline.flatMap((row) => [row.model_electrical_power_kw, row.observed_electrical_power_kw, ...(truthVisible ? [row.synthetic_truth_electrical_power_kw] : [])]).map((value) => value / 1000)
  const min = Math.floor((Math.min(...values) - 0.3) * 2) / 2
  const max = Math.ceil((Math.max(...values) + 0.3) * 2) / 2
  const x = (index: number) => margin.left + index / Math.max(timeline.length - 1, 1) * plotWidth
  const y = (value: number) => margin.top + (max - value / 1000) / (max - min) * (plotBottom - margin.top)
  const series = [
    { key: 'model_electrical_power_kw', label: 'Reference', cls: 'reference', values: timeline.map((row) => row.model_electrical_power_kw) },
    ...(truthVisible ? [{ key: 'synthetic_truth_electrical_power_kw', label: 'Synthetic truth', cls: 'truth', values: timeline.map((row) => row.synthetic_truth_electrical_power_kw) }] : []),
    { key: 'observed_electrical_power_kw', label: 'Observation', cls: 'observation', values: timeline.map((row) => row.observed_electrical_power_kw) },
  ]
  const paths = series.map((item) => ({ ...item, points: item.values.map((value, index) => `${x(index).toFixed(2)},${y(value).toFixed(2)}`).join(' ') }))
  const labelGap = 14
  const labelMin = margin.top + 7
  const labelMax = plotBottom - 5
  const labelEntries = paths.map((item) => ({ ...item, actualY: y(item.values.at(-1) ?? 0) })).sort((a, b) => a.actualY - b.actualY)
  const unshiftedLabels = labelEntries.reduce<Array<(typeof labelEntries)[number] & { labelY: number }>>((labels, item) => {
    const previousLabelY = labels.at(-1)?.labelY ?? labelMin - labelGap
    const labelY = Math.max(item.actualY, previousLabelY + labelGap)
    return [...labels, { ...item, labelY }]
  }, [])
  const labelShift = Math.max(0, (unshiftedLabels.at(-1)?.labelY ?? labelMin) - labelMax)
  const directLabels = unshiftedLabels.map((item) => ({ ...item, labelY: item.labelY - labelShift }))
  const selected = timeline[selectedIndex]
  const flaggedCount = timeline.filter((row) => row.anomaly_flag).length
  const minResidual = Math.min(...timeline.map((row) => row.power_residual_kw / 1000))
  const maxResidual = Math.max(...timeline.map((row) => row.power_residual_kw / 1000))
  const residualScale = Math.max(Math.abs(minResidual), Math.abs(maxResidual), 0.01)
  const zeroY = residualTop + 29
  const residualY = (value: number) => zeroY - value / residualScale * 22
  const summary = flaggedCount > 0
    ? `${flaggedCount} of ${timeline.length} samples are flagged by the residual screen; the selected observation is ${selected && selected.power_residual_kw < 0 ? 'below' : 'above'} the reference model.`
    : `No samples are flagged by the residual screen; the largest absolute residual is ${(Math.max(...timeline.map((row) => Math.abs(row.power_residual_kw))) / 1000).toFixed(2)} MW.`

  return (
    <div className="timeline-chart" ref={host}>
      <div className="timeline-chart-controls">
        <button type="button" className={`text-control ${truthVisible ? 'is-on' : ''}`} aria-pressed={truthVisible} onClick={onToggleTruth}>Synthetic truth {truthVisible ? 'shown' : 'hidden'}</button>
        <button type="button" className="text-control" aria-pressed={table} onClick={() => setTable((value) => !value)}>{table ? 'View chart' : 'View as table'}</button>
      </div>
      {table ? <div className="timeline-table-wrap"><table className="timeline-table"><thead><tr><th>Time (UTC)</th><th>Reference model (MW)</th><th>Synthetic observation (MW)</th><th>Residual (MW)</th><th>Screen</th></tr></thead><tbody>{timeline.map((row, index) => <tr key={row.timestamp_utc} className={index === selectedIndex ? 'is-selected' : ''}><td><button type="button" className="timeline-table-select" aria-label={`Select sample ${index + 1}, ${formatUtcTime(row.timestamp_utc)}`} onClick={() => onSelect(index)}>{formatUtcTime(row.timestamp_utc)}<span className="sr-only">, sample {index + 1}</span></button></td><td>{powerMw(row.model_electrical_power_kw)}</td><td>{powerMw(row.observed_electrical_power_kw)}</td><td className={row.power_residual_kw === 0 ? 'zero-value' : ''}>{signedNumber(row.power_residual_kw / 1000)}</td><td>{row.anomaly_flag ? 'Flagged by residual screen' : 'Not flagged'}</td></tr>)}</tbody></table></div> : <div className="chart-scroll"><svg className="responsive-chart-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Electrical output and residual screen across the synthetic timeline">
        {Array.from({ length: 5 }, (_, index) => {
          const value = max - (max - min) * index / 4
          const yy = margin.top + (plotBottom - margin.top) * index / 4
          return <g key={value}><line x1={margin.left} x2={width - margin.right} y1={yy} y2={yy} className="chart-grid" /><text x={margin.left - 9} y={yy + 4} textAnchor="end" className="chart-axis-label">{value.toFixed(1)}</text></g>
        })}
        <text x="10" y={margin.top - 8} className="chart-axis-label">MW</text>
        <line x1={margin.left} x2={width - margin.right} y1={plotBottom} y2={plotBottom} className="chart-axis-line" />
        <text x={margin.left} y={plotBottom + 19} className="chart-axis-label">{timeline[0] ? formatUtcTime(timeline[0].timestamp_utc) : ''}</text>
        <text x={width - margin.right} y={plotBottom + 19} textAnchor="end" className="chart-axis-label">{timeline.at(-1) ? formatUtcTime(timeline.at(-1)!.timestamp_utc) : ''}</text>
        {paths.map((item) => <polyline key={item.key} points={item.points} className={`timeline-line line-${item.cls}`} fill="none" />)}
        {directLabels.map((item) => <g key={`${item.key}-label`} className={`direct-${item.cls}`}><path d={`M ${width - margin.right} ${item.actualY} L ${width - margin.right + 5} ${item.labelY}`} className="direct-label-connector" /><text x={width - margin.right + 9} y={item.labelY + 4} className="direct-label">{item.label}</text></g>)}
        {selected && <g><line x1={x(selectedIndex)} x2={x(selectedIndex)} y1={margin.top} y2={plotBottom} className="chart-playhead" /><circle cx={x(selectedIndex)} cy={y(selected.observed_electrical_power_kw)} r="4" className="chart-selected-point" /></g>}
        <text x="10" y={residualTop + 9} className="chart-axis-label">Residual</text>
        <line x1={margin.left} x2={width - margin.right} y1={zeroY} y2={zeroY} className="residual-zero" />
        {timeline.map((row, index) => {
          const xx = x(index)
          const yy = residualY(row.power_residual_kw / 1000)
          return <g key={`residual-${index}`}><line x1={xx} x2={xx} y1={zeroY} y2={yy} className={`residual-mark ${row.anomaly_flag ? 'is-flagged' : ''}`} />{row.anomaly_flag && <path d={flagShape(xx, yy)} className="flag-marker"><title>Flagged by residual screen, sample {index + 1}</title></path>}</g>
        })}
        {selected && <line x1={x(selectedIndex)} x2={x(selectedIndex)} y1={residualTop} y2={height - 10} className="chart-playhead" />}
        <text x={margin.left} y={height - 1} className="chart-axis-label">{timeline[0] ? formatUtcTime(timeline[0].timestamp_utc) : ''}</text>
        <text x={width - margin.right} y={height - 1} textAnchor="end" className="chart-axis-label">{timeline.at(-1) ? formatUtcTime(timeline.at(-1)!.timestamp_utc) : ''}</text>
      </svg></div>}
      <p className="trend-summary">{summary}</p>
      {selected && <div className="chart-readout" aria-label="Selected sample readout"><span>{formatUtcTime(selected.timestamp_utc)}</span><span>Reference <ValueWithUnit value={powerMw(selected.model_electrical_power_kw)} unit="MW" /></span><span>Observation <ValueWithUnit value={powerMw(selected.observed_electrical_power_kw)} unit="MW" /></span><span className={selected.power_residual_kw === 0 ? 'zero-value' : ''}>Residual <ValueWithUnit value={signedNumber(selected.power_residual_kw / 1000)} unit="MW" /></span></div>}
    </div>
  )
}

function TimelineCard({ timeline, selectedIndex, isPlaying, setPlaying, onSelect }: { timeline: TimelinePoint[]; selectedIndex: number; isPlaying: boolean; setPlaying: (value: boolean) => void; onSelect: (index: number) => void }) {
  const liveRef = useRef<HTMLParagraphElement>(null)
  const [helpOpen, setHelpOpen] = useState(false)
  const [truthVisible, setTruthVisible] = useState(true)
  const count = timeline.length
  const flagged = timeline.some((row) => row.anomaly_flag)
  const selected = timeline[selectedIndex]
  useEffect(() => {
    if (isPlaying || !selected || !liveRef.current) return
    const timer = window.setTimeout(() => { if (liveRef.current) liveRef.current.textContent = `Sample ${selectedIndex + 1} of ${count}, ${formatUtcTime(selected.timestamp_utc)}.` }, 450)
    return () => window.clearTimeout(timer)
  }, [selectedIndex, count, isPlaying, selected])
  useEffect(() => {
    if (!isPlaying || count === 0) return
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const timer = window.setTimeout(() => {
      if (selectedIndex >= count - 1) setPlaying(false)
      else onSelect(selectedIndex + 1)
    }, reducedMotion ? 800 : 360)
    return () => window.clearTimeout(timer)
  }, [isPlaying, selectedIndex, count, onSelect, setPlaying])
  const jumpFlag = () => {
    const index = timeline.findIndex((row) => row.anomaly_flag)
    if (index >= 0) { onSelect(index); setPlaying(false) }
  }
  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    const formTarget = event.target instanceof HTMLInputElement || event.target instanceof HTMLButtonElement || event.target instanceof HTMLSelectElement
    if (formTarget && event.key.toLowerCase() !== 'f' && event.code !== 'Space') return
    let next: number | null = null
    if (event.key === 'ArrowLeft') next = selectedIndex - (event.shiftKey ? 10 : 1)
    else if (event.key === 'ArrowRight') next = selectedIndex + (event.shiftKey ? 10 : 1)
    else if (event.key === 'Home') next = 0
    else if (event.key === 'End') next = count - 1
    else if (event.key.toLowerCase() === 'f') { event.preventDefault(); if (flagged) jumpFlag(); return }
    else if (event.code === 'Space') { event.preventDefault(); setPlaying(!isPlaying); return }
    else return
    event.preventDefault()
    onSelect(Math.max(0, Math.min(count - 1, next)))
  }
  return (
    <section className="timeline-card panel" aria-labelledby="timeline-title" tabIndex={0} onKeyDown={onKeyDown}>
      <div className="timeline-heading"><div><h2 id="timeline-title">Electrical output over 24 hours</h2><p>Where does the observation depart from the reference?</p></div>
        <div className="timeline-actions"><button type="button" className="icon-action" aria-label="Replay keyboard shortcuts" aria-expanded={helpOpen} onClick={() => setHelpOpen((open) => !open)}><CircleHelp size={17} aria-hidden="true" /></button><button type="button" className="button button-quiet replay-button" onClick={() => setPlaying(!isPlaying)}>{isPlaying ? <Pause size={14} aria-hidden="true" /> : <Play size={14} aria-hidden="true" />}{isPlaying ? 'Pause replay' : 'Play replay'}</button></div>
      </div>
      {helpOpen && <div className="shortcut-popover" role="status"><strong>Replay keys</strong><span>Left / Right: one sample</span><span>Shift + Left / Right: ten samples</span><span>Home / End: first / last sample</span><span>Space: play or pause</span><span className={!flagged ? 'is-disabled' : ''}>F: first flagged sample{!flagged ? ' (none flagged)' : ''}</span></div>}
      <TimelineChart timeline={timeline} selectedIndex={selectedIndex} truthVisible={truthVisible} onSelect={(index) => { setPlaying(false); onSelect(index) }} onToggleTruth={() => setTruthVisible((visible) => !visible)} />
      <div className="timeline-scrubber-row"><label htmlFor="sample-range">Sample {selectedIndex + 1} of {count}</label><input id="sample-range" type="range" min="0" max={count - 1} value={selectedIndex} aria-label="Scenario sample" aria-valuetext={selected ? `Sample ${selectedIndex + 1} of ${count}; ${formatUtcTime(selected.timestamp_utc)} UTC; reference ${powerMw(selected.model_electrical_power_kw)} megawatts; observation ${powerMw(selected.observed_electrical_power_kw)} megawatts; residual ${signedNumber(selected.power_residual_kw / 1000)} megawatts` : 'No sample selected'} onKeyDown={(event) => { if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); onSelect(Math.max(0, Math.min(count - 1, selectedIndex + (event.key === 'ArrowLeft' ? -1 : 1) * (event.shiftKey ? 10 : 1)))) } }} onChange={(event) => { setPlaying(false); onSelect(Number(event.target.value)) }} /></div>
      <button className="first-flag-button" type="button" onClick={jumpFlag} disabled={!flagged}>First flagged sample</button>
      <p ref={liveRef} className="sr-only" aria-live="polite" aria-atomic="true">Sample {selectedIndex + 1} of {count}.</p>
    </section>
  )
}

function RunState() {
  const { state, retry } = useTurbineStore()
  if (state.engineStatus === 'offline') return <div className="engine-banner" role="alert"><strong>Local engine offline.</strong> Start it with <code>.\.venv\Scripts\python.exe -m uvicorn turbineiq.api.main:app --host 127.0.0.1 --port 8000</code> and retry the request.</div>
  if (state.requestError) return <div className="request-banner" role="alert"><span>The run request returned an error: {state.requestError}</span><button className="button button-quiet" type="button" onClick={retry}>Retry</button></div>
  return null
}

function OverviewLoading() {
  return <div className="overview-skeletons" aria-label="Loading synthetic run"><div className="skeleton-line" /><div className="skeleton-kpis"><i /><i /><i /><i /></div><div className="skeleton-stage" /><div className="skeleton-chart" /></div>
}

export function ComponentDetail() {
  const { state, selectComponent } = useTurbineStore()
  const snapshot = state.run?.snapshots[state.sampleIndex]
  const id = state.componentId ?? 'compressor'
  const component = snapshot?.components.find((item) => item.component_id === id)
  if (!snapshot || !component) return <OverviewLoading />
  return <section className="component-detail panel"><div className="card-heading"><h2>{component.label}</h2><span className="neutral-status">Synthetic</span></div><p>{component.summary}</p><div className="component-detail-metrics">{component.metrics.map((metric) => <div key={metric.key}><span>{metric.label}</span><ValueWithUnit value={metricValue(metric)} unit={typeof metric.value === 'boolean' || metric.key.includes('efficiency') ? undefined : metric.unit} />{metric.reference_value !== null && <small><ReferenceMetric metric={metric} /></small>}<small>{metric.provenance}</small></div>)}</div><button type="button" className="text-control" onClick={() => selectComponent(id)}>Select {component.label} in the overview</button></section>
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
  if (!run || !snapshot) return <div className="overview-page" id="route-outlet"><RunState />{state.engineStatus !== 'offline' && !state.requestError && <OverviewLoading />}</div>
  const selectKnownComponent = (id: string) => {
    if (['inlet', 'compressor', 'combustor', 'turbine', 'shaft', 'generator'].includes(id)) selectComponent(id as ComponentId)
  }
  return (
    <div className="overview-page" id="route-outlet">
      <RunState />
      <FilterRow sample={snapshot} stopPlayback={() => setPlaying(false)} />
      <KpiRow snapshot={snapshot} timeline={run.timeline} />
      {state.requestError && <p className="stale-run-note">The previous successful run remains visible until a new request succeeds.</p>}
      <div className="overview-band">
        <div className="stage-column">
          <Suspense fallback={<section className="viewer-panel panel stage-skeleton" aria-label="Loading turbine stage"><div className="skeleton-stage" /></section>}>
            <TurbineViewer components={snapshot.components} selectedComponentId={viewSelectedId} onSelectComponent={selectKnownComponent} />
          </Suspense>
          <StationLedger snapshot={snapshot} timelineRow={timelineRow} selectedComponentId={selectedId} hoveredComponent={hoveredComponent} onSelect={selectComponent} onHover={setHoveredComponent} />
        </div>
        <ComponentLedger snapshot={snapshot} selectedId={selectedId} onSelect={selectComponent} />
      </div>
      <TimelineCard timeline={run.timeline} selectedIndex={state.sampleIndex} isPlaying={isPlaying} setPlaying={setPlaying} onSelect={selectSample} />
      <span className="sr-only">{hoveredComponent ? `Highlighting ${hoveredComponent} on the Stage.` : ''}</span>
      <span className="sr-only">Scenario {run.run.scenario_name}, seed {run.run.seed}, sample {state.sampleIndex + 1}.</span>
      {state.loading && <span className="run-refresh-status" role="status">A new synthetic run is being prepared.</span>}
    </div>
  )
}
