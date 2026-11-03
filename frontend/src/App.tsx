import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import {
  BookOpen,
  Bot,
  ChevronRight,
  Database,
  Gauge,
  Info,
  Pause,
  Play,
  Search,
  ShieldCheck,
  Sparkles,
  Wind,
  Zap,
} from 'lucide-react'
import { api } from './api'
import { PowerChart } from './PowerChart'
import type {
  AssistantResponse,
  EvidenceHit,
  ScenarioDefinition,
  SelectedTwinSelection,
  TwinComponentState,
  TwinMetric,
  TwinRunPayload,
  TwinSnapshot,
} from './types'
import './TurbineIQ.css'

const TurbineViewer = lazy(() => import('./TurbineViewer').then((module) => ({ default: module.TurbineViewer })))

type WorkspacePage = 'twin' | 'evidence'

function formatMW(kw: number): string {
  return `${(kw / 1000).toFixed(2)} MW`
}

function formatClock(value: string): string {
  return new Date(value).toLocaleString([], {
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'UTC',
    timeZoneName: 'short',
  })
}

function formatMetric(metric: TwinMetric): string {
  if (typeof metric.value === 'boolean') return metric.value ? 'Yes' : 'No'
  const isEfficiency = metric.key.includes('efficiency')
  if (isEfficiency) return `${(metric.value * 100).toFixed(1)}%`
  return `${metric.value.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${metric.unit}`
}

function formatReference(metric: TwinMetric): string | null {
  if (metric.reference_value === null) return null
  const isEfficiency = metric.key.includes('efficiency')
  if (isEfficiency) return `${(metric.reference_value * 100).toFixed(1)}% reference`
  return `${metric.reference_value.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${metric.unit} reference`
}

function componentTone(status: string): string {
  if (status === 'scenario_perturbation') return 'tone-warning'
  if (status === 'residual_screen' || status === 'synthetic_measurement_fault') return 'tone-alert'
  if (status === 'scenario_context') return 'tone-context'
  return 'tone-neutral'
}

function MetricCard({ label, value, detail, tone = '' }: {
  label: string
  value: string
  detail: string
  tone?: string
}) {
  return (
    <div className={`metric-card ${tone}`}>
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      <div className="metric-detail">{detail}</div>
    </div>
  )
}

function ComponentInspector({
  component,
  components,
  selectedComponentId,
  onSelectComponent,
}: {
  component: TwinComponentState
  components: TwinComponentState[]
  selectedComponentId: string
  onSelectComponent: (componentId: string) => void
}) {
  return (
    <section className="inspector-panel panel">
      <div className="panel-heading">
        <div>
          <h2>{component.label}</h2>
        </div>
        <span className={`status-badge ${componentTone(component.status)}`}>
          <span className="state-dot" />{component.status_label}
        </span>
      </div>
      <p className="component-summary">{component.summary}</p>
      <div className="component-metrics">
        {component.metrics.map((metric) => (
          <div className="component-metric" key={metric.key}>
            <div className="component-metric-main">
              <span>{metric.label}</span>
              <strong>{formatMetric(metric)}</strong>
            </div>
            {formatReference(metric) && <div className="metric-reference">{formatReference(metric)}</div>}
            <div className="metric-provenance">{metric.provenance}</div>
          </div>
        ))}
      </div>
      <section className="inspector-section" aria-label="Turbine sections">
        <div className="inspector-section-title">Turbine sections</div>
        <div className="component-strip">
          {components.map((item) => (
            <button
              key={item.component_id}
              type="button"
              className={`component-chip ${selectedComponentId === item.component_id ? 'is-selected' : ''}`}
              aria-pressed={selectedComponentId === item.component_id}
              onClick={() => onSelectComponent(item.component_id)}
            >
              <span className={`component-marker marker-${item.status}`} />
              {item.label}
            </button>
          ))}
        </div>
      </section>
      <section className="inspector-reference" aria-label="Published GE 6B.03 reference ratings">
        <div className="inspector-section-title">Published 6B.03 reference</div>
        <div className="reference-spec-values">
          <span><span>Net output</span><strong>45 MW</strong></span>
          <span><span>LHV efficiency</span><strong>33.4%</strong></span>
          <span><span>Pressure ratio</span><strong>12.8:1</strong></span>
          <span><span>Exhaust temperature</span><strong>561°C</strong></span>
          <span><span>Exhaust flow</span><strong>145.1 kg/s</strong></span>
        </div>
        <div className="reference-spec-note">GE catalog ratings at ISO conditions on natural gas. The synthetic replay is not calibrated to these values; model geometry is conceptual, not dimensioned OEM layout.</div>
      </section>
      <div className="inspector-rule" />
      <div className="inspector-meta">
        <span><Database size={13} /> {component.metrics.length} mapped values</span>
        <span><ShieldCheck size={13} /> Synthetic only</span>
      </div>
    </section>
  )
}

function EvidenceWorkspace({
  evidence,
  setEvidence,
  selectedTwin,
}: {
  evidence: EvidenceHit[]
  setEvidence: (hits: EvidenceHit[]) => void
  selectedTwin: SelectedTwinSelection | null
}) {
  const [query, setQuery] = useState('Brayton cycle assumptions')
  const [searching, setSearching] = useState(false)
  const [searchMessage, setSearchMessage] = useState('')
  const [question, setQuestion] = useState('Explain the compressor-efficiency drift result.')
  const [enableCloud, setEnableCloud] = useState(false)
  const [allowCloudDocs, setAllowCloudDocs] = useState(false)
  const [answer, setAnswer] = useState<AssistantResponse | null>(null)
  const [asking, setAsking] = useState(false)

  const runSearch = async () => {
    setSearching(true)
    setSearchMessage('')
    try {
      const result = await api.evidence(query)
      setEvidence(result.evidence)
      setSearchMessage(result.no_evidence ? 'No supporting passage found in the local notes.' : `${result.evidence.length} cited passages from local notes.`)
    } catch (error) {
      setSearchMessage(error instanceof Error ? error.message : 'Evidence search failed.')
    } finally {
      setSearching(false)
    }
  }

  const ask = async () => {
    setAsking(true)
    setAnswer(null)
    try {
      setAnswer(await api.ask(question, enableCloud, enableCloud && allowCloudDocs, selectedTwin))
    } catch (error) {
      setAnswer({
        answer: error instanceof Error ? error.message : 'The assistant request failed.',
        mode: 'error',
        warning: null,
        tool_calls: [],
        synthetic_only: true,
      })
    } finally {
      setAsking(false)
    }
  }

  useEffect(() => {
    void runSearch()
    // Load the documented model assumptions once when this view mounts.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="evidence-page">
      <div className="page-title-row">
        <div>
          <h1>Evidence workspace</h1>
          <p>Search local engineering notes and ask the bounded assistant to explain generated results.</p>
        </div>
        <span className="mode-badge"><BookOpen size={14} /> Local-first retrieval</span>
      </div>
      <div className="evidence-grid">
        <section className="panel evidence-panel">
          <div className="panel-heading">
            <div>
              <h2>Local cited retrieval</h2>
            </div>
            <span className="small-badge"><Database size={13} /> No cloud search</span>
          </div>
          <p className="panel-description">Search the bundled synthetic notes. Results stay in this local service and include their source section.</p>
          <form className="search-form" onSubmit={(event) => { event.preventDefault(); void runSearch() }}>
            <Search size={16} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} aria-label="Search local documents" />
            <button className="button button-primary" type="submit" disabled={searching || query.trim().length < 2}>
              {searching ? 'Searching' : 'Search'}
            </button>
          </form>
          <div className="inline-message" aria-live="polite">{searchMessage}</div>
          <div className="evidence-list">
            {evidence.map((hit, index) => (
              <article className="evidence-hit" key={`${hit.source}-${hit.citation}-${index}`}>
                <div className="evidence-hit-head">
                  <span className="citation-tag">{hit.citation}</span>
                  <span className="relevance-score">{hit.score.toFixed(2)} relevance</span>
                </div>
                <p>{hit.text}</p>
              </article>
            ))}
            {evidence.length === 0 && <div className="empty-evidence">Search for a model assumption or a section title to see cited passages.</div>}
          </div>
        </section>
        <section className="panel assistant-panel">
          <div className="panel-heading">
            <div>
              <h2>Ask about this prototype</h2>
            </div>
            <span className="small-badge"><Bot size={14} /> Tool allow-list</span>
          </div>
          <p className="panel-description">Numerical results come from local engineering tools. The assistant cannot connect to equipment or issue actions.</p>
          <label className="field-label" htmlFor="assistant-question">Question</label>
          <textarea id="assistant-question" value={question} onChange={(event) => setQuestion(event.target.value)} rows={4} />
          <div className="cloud-controls">
            <label className="toggle-row">
              <input type="checkbox" checked={enableCloud} onChange={(event) => setEnableCloud(event.target.checked)} />
              <span>Use configured cloud language model</span>
            </label>
            <p>When enabled, your question and current synthetic sample/component context are sent to the configured provider. Document excerpts require the separate option below.</p>
            {enableCloud && (
              <label className="toggle-row toggle-secondary">
                <input type="checkbox" checked={allowCloudDocs} onChange={(event) => setAllowCloudDocs(event.target.checked)} />
                <span>Also include retrieved document excerpts</span>
              </label>
            )}
          </div>
          <button type="button" className="button button-primary ask-button" onClick={() => void ask()} disabled={asking || !question.trim()}>
            <Sparkles size={15} /> {asking ? 'Working locally…' : 'Ask TurbineIQ'}
          </button>
          {answer && (
            <div className="assistant-answer" aria-live="polite">
              <div className="answer-meta"><span className="citation-tag">{answer.mode.replaceAll('_', ' ')}</span><span>Generated data only</span></div>
              <p>{answer.answer}</p>
              {answer.warning && <div className="warning-note"><Info size={14} />{answer.warning}</div>}
              {answer.tool_calls.length > 0 && <details><summary>Tool trace · {answer.tool_calls.length} call(s)</summary><pre>{answer.tool_calls.map((call) => `${call.name}\n${JSON.stringify(call.result, null, 2)}`).join('\n\n')}</pre></details>}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}

function App() {
  const [page, setPage] = useState<WorkspacePage>('twin')
  const [scenarios, setScenarios] = useState<ScenarioDefinition[]>([])
  const [scenarioId, setScenarioId] = useState('compressor_fouling')
  const [seedInput, setSeedInput] = useState('42')
  const [run, setRun] = useState<TwinRunPayload | null>(null)
  const [sampleIndex, setSampleIndex] = useState(72)
  const [selectedComponentId, setSelectedComponentId] = useState('compressor')
  const [isPlaying, setIsPlaying] = useState(false)
  const [loading, setLoading] = useState(true)
  const [apiStatus, setApiStatus] = useState<'checking' | 'ok' | 'offline'>('checking')
  const [errorMessage, setErrorMessage] = useState('')
  const [evidence, setEvidence] = useState<EvidenceHit[]>([])

  const seed = Number.parseInt(seedInput, 10)
  const validSeed = Number.isInteger(seed) && seed >= 0

  useEffect(() => {
    let active = true
    Promise.all([api.health(), api.scenarios()])
      .then(([health, definitions]) => {
        if (!active) return
        setApiStatus(health.status === 'ok' ? 'ok' : 'offline')
        setScenarios(definitions)
      })
      .catch(() => { if (active) setApiStatus('offline') })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!validSeed) return
    let active = true
    api.run(scenarioId, seed)
      .then((payload) => {
        if (!active) return
        setRun(payload)
        setSampleIndex(scenarioId === 'compressor_fouling' ? 72 : 48)
        setSelectedComponentId((current) => payload.snapshot.components.some((item) => item.component_id === current) ? current : 'compressor')
      })
      .catch((error) => {
        if (active) setErrorMessage(error instanceof Error ? error.message : 'Could not generate the synthetic run.')
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [scenarioId, seed, validSeed])

  useEffect(() => {
    if (!isPlaying || !run) return
    const timer = window.setTimeout(() => {
      if (sampleIndex >= run.run.sample_count - 1) {
        setSampleIndex(0)
        setIsPlaying(false)
      } else {
        setSampleIndex(sampleIndex + 1)
      }
    }, 360)
    return () => window.clearTimeout(timer)
  }, [isPlaying, sampleIndex, run])

  const snapshot: TwinSnapshot | null = run?.snapshots[sampleIndex] ?? null
  const selectedComponent = snapshot?.components.find((item) => item.component_id === selectedComponentId)
    ?? snapshot?.components[0]
    ?? null
  const selectedTwin: SelectedTwinSelection | null = snapshot && selectedComponent
    ? {
      scenario_id: snapshot.scenario_id,
      seed: snapshot.seed,
      sample_index: snapshot.sample_index,
      selected_component_id: selectedComponent.component_id,
    }
    : null
  const flaggedSamples = useMemo(() => run?.timeline.filter((point) => point.anomaly_flag).length ?? 0, [run])
  const firstFlaggedSample = useMemo(() => run?.timeline.findIndex((point) => point.anomaly_flag) ?? -1, [run])
  const scenario = scenarios.find((item) => item.scenario_id === scenarioId)
  const residualTone = snapshot?.residual_screen_flag ? 'tone-alert' : 'tone-neutral'
  const residualValue = snapshot ? `${snapshot.power_residual_kw >= 0 ? '+' : ''}${(snapshot.power_residual_kw / 1000).toFixed(2)} MW` : '—'

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="TurbineIQ workspace navigation">
        <div className="brand-lockup" title="TurbineIQ">
          <span className="brand-mark"><Wind size={19} strokeWidth={1.7} /></span>
          <span className="brand-name">TurbineIQ</span>
        </div>
        <div className="side-divider" />
        <nav className="primary-nav" aria-label="Primary navigation">
          <button
            className={`nav-item ${page === 'twin' ? 'active' : ''}`}
            aria-label="Twin workbench"
            aria-current={page === 'twin' ? 'page' : undefined}
            title="Twin workbench"
            onClick={() => setPage('twin')}
          >
            <Gauge size={18} /><span className="nav-item-label">Twin workbench</span>
          </button>
          <button
            className={`nav-item ${page === 'evidence' ? 'active' : ''}`}
            aria-label="Evidence and assistant"
            aria-current={page === 'evidence' ? 'page' : undefined}
            title="Evidence and assistant"
            onClick={() => setPage('evidence')}
          >
            <BookOpen size={18} /><span className="nav-item-label">Evidence & assistant</span>
          </button>
        </nav>
        <div className="sidebar-spacer" />
        <div
          className="rail-status"
          role="status"
          aria-label={apiStatus === 'ok' ? 'Local engine connected' : apiStatus === 'offline' ? 'Local API unavailable' : 'Checking local engine'}
          title={apiStatus === 'ok' ? 'Local engine connected' : apiStatus === 'offline' ? 'Local API unavailable' : 'Checking local engine'}
        >
          <span className={`status-indicator ${apiStatus}`} />
        </div>
        <div className="scope-mark" title="Synthetic data only · no physical connection or control" aria-label="Synthetic data only; no physical connection or control">
          <ShieldCheck size={16} />
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumb"><span>TurbineIQ</span><ChevronRight size={13} /><strong>{page === 'twin' ? 'Twin workbench' : 'Evidence & assistant'}</strong></div>
          <div className="topbar-right"><span className="mode-badge"><span className="state-dot" /> Synthetic data</span><span className="topbar-divider" /><span className="local-chip"><span className={`status-indicator ${apiStatus}`} /> Local engine</span></div>
        </header>

        {errorMessage && <div className="error-banner" role="alert"><Info size={15} />{errorMessage}</div>}
        {page === 'evidence' ? (
          <EvidenceWorkspace evidence={evidence} setEvidence={setEvidence} selectedTwin={selectedTwin} />
        ) : (
          <div className="workspace-page">
            <div className="page-title-row twin-title-row">
              <div>
                <h1>Gas turbine workbench</h1>
                <p>Simplified open-cycle model · selected sample {snapshot ? formatClock(snapshot.timestamp_utc) : 'loading'}</p>
              </div>
              <div className="scenario-controls" aria-label="Synthetic scenario controls">
                <label className="scenario-field" htmlFor="scenario-select">
                  <span>Scenario</span>
                  <select id="scenario-select" value={scenarioId} onChange={(event) => { setLoading(true); setRun(null); setIsPlaying(false); setErrorMessage(''); setScenarioId(event.target.value) }}>
                    {scenarios.map((item) => <option key={item.scenario_id} value={item.scenario_id}>{item.name}</option>)}
                    {scenarios.length === 0 && <option value="compressor_fouling">Compressor-performance drift</option>}
                  </select>
                </label>
                <label className="scenario-field seed-field" htmlFor="seed-input">
                  <span>Seed</span>
                  <input
                    id="seed-input"
                    inputMode="numeric"
                    value={seedInput}
                    onChange={(event) => {
                      const value = event.target.value
                      const parsed = Number.parseInt(value, 10)
                      setLoading(Number.isInteger(parsed) && parsed >= 0)
                      setRun(null)
                      setIsPlaying(false)
                      setErrorMessage('')
                      setSeedInput(value)
                    }}
                    aria-invalid={!validSeed}
                  />
                </label>
                <span className="sample-context">{run?.run.sample_count ?? 96} samples · 15 min</span>
              </div>
            </div>
            {!validSeed && <div className="field-error seed-error">Enter a non-negative integer.</div>}
            {scenario && <p className="scenario-description">{scenario.description}</p>}

            {snapshot && (
              <>
                <div className="metric-row">
                  <MetricCard label="Reference model" value={formatMW(snapshot.model_electrical_power_kw)} detail="Fixed assumptions" />
                  <MetricCard label="Synthetic observation" value={formatMW(snapshot.synthetic_observed_power_kw)} detail="Model output + generated noise" />
                  <MetricCard label="Observation residual" value={residualValue} detail="Observation − reference" tone={residualTone} />
                  <MetricCard label="Flagged samples" value={`${flaggedSamples} / ${run?.run.sample_count ?? 96}`} detail="Median absolute deviation screen" tone={flaggedSamples > 0 ? 'tone-alert' : ''} />
                </div>

                <div className="visual-workspace">
                  <Suspense fallback={<div className="viewer-module-loading panel">Loading interactive 3D viewer…</div>}>
                    <TurbineViewer
                      components={snapshot.components}
                      selectedComponentId={selectedComponentId}
                      onSelectComponent={setSelectedComponentId}
                    />
                  </Suspense>
                  {selectedComponent && (
                    <ComponentInspector
                      component={selectedComponent}
                      components={snapshot.components}
                      selectedComponentId={selectedComponentId}
                      onSelectComponent={setSelectedComponentId}
                    />
                  )}
                </div>

                <section className="timeline-panel panel">
                  <div className="timeline-heading">
                    <div>
                      <h2>Electrical output over 24 hours</h2>
                    </div>
                    <div className="timeline-tools">
                      <span className="time-readout">{formatClock(snapshot.timestamp_utc)}</span>
                      <button type="button" className="button button-quiet play-button" onClick={() => setIsPlaying((playing) => !playing)}>
                        {isPlaying ? <Pause size={14} /> : <Play size={14} />}{isPlaying ? 'Pause replay' : 'Play replay'}
                      </button>
                    </div>
                  </div>
                  {loading ? <div className="chart-loading">Generating reproducible scenario…</div> : run && <PowerChart timeline={run.timeline} selectedIndex={sampleIndex} />}
                  <div className="scrubber-row">
                    <span className="scrubber-edge">00:00</span>
                    <input
                      className="timeline-scrubber"
                      type="range"
                      min={0}
                      max={(run?.run.sample_count ?? 96) - 1}
                      value={sampleIndex}
                      onChange={(event) => { setIsPlaying(false); setSampleIndex(Number(event.target.value)) }}
                      aria-label="Scenario timeline sample"
                    />
                    <span className="scrubber-edge">24:00</span>
                    <span className="sample-count">{sampleIndex + 1} / {run?.run.sample_count ?? 96}</span>
                  </div>
                  <div className="timeline-events">
                    <div className="event-label"><span className="event-tick" />{run?.run.scenario_name}</div>
                    <span className="event-description">{run?.run.scenario_description}</span>
                    {firstFlaggedSample >= 0 && <button type="button" className="flag-link" onClick={() => setSampleIndex(firstFlaggedSample)}><Zap size={13} /> First residual flag · sample {firstFlaggedSample + 1}</button>}
                  </div>
                </section>

                <div className="trust-strip">
                  <div><span className="trust-icon"><ShieldCheck size={14} /></span><span><strong>Provenance</strong> {snapshot.data_provenance} · seed {snapshot.seed}</span></div>
                  <div><span className="trust-icon"><Info size={14} /></span><span><strong>Model boundary</strong> {run?.run.model_name} · not OEM-validated</span></div>
                  <button type="button" className="text-link" onClick={() => setPage('evidence')}>Open evidence workspace <ChevronRight size={14} /></button>
                </div>
              </>
            )}
            {!snapshot && (
              <div className="loading-state">
                <div className="loading-rule" />
                <p>{loading ? 'Building the synthetic operating sequence locally…' : !validSeed ? 'Enter a valid non-negative seed to generate a run.' : 'The synthetic run is unavailable. Check the local API and try again.'}</p>
              </div>
            )}
          </div>
        )}
        <footer className="app-footer"><span>TurbineIQ · local engineering prototype</span><span>Simplified model · synthetic data · no physical connection or control</span></footer>
      </main>
    </div>
  )
}

export default App
