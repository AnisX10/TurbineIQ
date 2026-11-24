import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Check, CircleAlert, History, OctagonAlert, Pause, Play, Power, RotateCcw, SlidersHorizontal, TriangleAlert, X, Zap } from 'lucide-react'
import { useTurbineStore } from '../../app/useTurbineStore'
import { routeHash } from '../../app/router'
import { EngineOfflineBanner } from '../../components/ui/EngineOfflineBanner'
import { Sheet } from '../../components/ui/Sheet'
import { twinApi } from '../../api'
import { FaultPanel } from '../operate/FaultPanel'
import { isAllowed, parseBounded, stateTone } from '../operate/simLogic'
import { LiveTurbine } from './LiveTurbine'
import { TwinTrend } from './TwinTrend'
import type { Decision, SupervisorMode, SupervisorSummary } from './supervisorTypes'
import { SUPERVISOR_MODES } from './supervisorTypes'
import type { Tone } from './twinLogic'
import {
  CHECK_LABELS,
  MODE_HINTS,
  MODE_LABELS,
  PROBLEM_LABELS,
  STATUS_LABELS,
  currentRecommendation,
  displayedMode,
  formatClock,
  kToC,
  rankComponents,
  stageCallouts,
  stateLabel,
  tripLabel,
  unitNow,
} from './twinLogic'
import { useTwinSession } from './useTwinSession'
import type { TwinSession } from './useTwinSession'
import '../operate/Operate.css'
import './TwinConsole.css'

const SPEEDS = [1, 10, 60] as const
const MAX_DEMAND_MW = 47

function useReducedMotion(): boolean {
  const [reduce, setReduce] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setReduce(query.matches)
    query.addEventListener('change', update)
    return () => query.removeEventListener('change', update)
  }, [])
  return reduce
}

function ToneMark({ tone }: { tone: Tone }) {
  if (tone === 'alarm') return <span className="twin-tone-mark is-alarm"><OctagonAlert size={13} aria-hidden="true" />Alarm</span>
  if (tone === 'warning') return <span className="twin-tone-mark is-warning"><TriangleAlert size={13} aria-hidden="true" />Warning</span>
  return null
}

function StartCard({ busy, onCreate }: { busy: boolean; onCreate: (mode: SupervisorMode) => void }) {
  const [mode, setMode] = useState<SupervisorMode>('advisory')
  return (
    <section className="twin-card twin-start" aria-labelledby="twin-start-title">
      <h2 id="twin-start-title">Start a live twin</h2>
      <p className="twin-note">
        Creates a simulated GE 6B.03-class unit held in memory, with the prescriptive layer watching it through its instruments.
        Nothing here is connected to a real machine.
      </p>
      <div className="twin-start-row">
        <ModeSwitch value={mode} pending={null} onChange={setMode} />
        <button className="twin-primary" type="button" disabled={busy} onClick={() => onCreate(mode)}>Create unit</button>
      </div>
      <p className="twin-note">{MODE_HINTS[mode]}</p>
    </section>
  )
}

function ModeSwitch({ value, pending, onChange, disabled = false }: { value: SupervisorMode | null; pending: SupervisorMode | null; onChange: (mode: SupervisorMode) => void; disabled?: boolean }) {
  return (
    <div className="twin-mode" role="group" aria-label="Layer mode">
      {SUPERVISOR_MODES.map((mode) => (
        <button
          key={mode}
          type="button"
          aria-pressed={value === mode}
          className={`${value === mode ? 'is-active' : ''} ${pending === mode ? 'is-pending' : ''}`}
          disabled={disabled}
          onClick={() => onChange(mode)}
        >
          {MODE_LABELS[mode]}
        </button>
      ))}
    </div>
  )
}

function ControlStrip({ sim, onFaults, onLog }: { sim: TwinSession; onFaults: () => void; onLog: () => void }) {
  const state = sim.state!
  const [demand, setDemand] = useState(() => (sim.summary?.demand_mw ?? 35).toString())
  const [demandError, setDemandError] = useState('')
  const can = (command: string) => isAllowed(state, command) && !sim.busy
  const submit = (event: FormEvent) => {
    event.preventDefault()
    const mw = parseBounded(demand, 0, MAX_DEMAND_MW)
    setDemandError(mw === null ? `Enter 0 to ${MAX_DEMAND_MW} MW.` : '')
    if (mw !== null) void sim.setDemand(mw)
  }
  const { state: app } = useTurbineStore()
  const operateHref = routeHash({ ...app, page: 'operate', componentId: app.componentId })
  return (
    <section className="twin-strip" aria-label="Unit controls">
      <div className="twin-strip-group">
        <span className={`operate-pill is-${stateTone(state.state)}`} data-testid="twin-unit-state">{stateLabel(state)}</span>
        <span className="twin-clock" aria-label="Simulated time">{formatClock(state.t_s)}</span>
      </div>
      <div className="twin-strip-group">
        {can('reset') ? (
          <button type="button" className="twin-button" onClick={() => void sim.send('reset')}><RotateCcw size={14} aria-hidden="true" />Reset trip</button>
        ) : can('stop') ? (
          <button type="button" className="twin-button" onClick={() => void sim.send('stop')}><Power size={14} aria-hidden="true" />Stop</button>
        ) : (
          <button type="button" className="twin-button" disabled={!can('start')} onClick={() => void sim.send('start')}><Power size={14} aria-hidden="true" />Start</button>
        )}
        <button className="twin-button twin-run" type="button" onClick={() => sim.setRunning(!sim.running)} aria-pressed={sim.running}>
          {sim.running ? <Pause size={14} aria-hidden="true" /> : <Play size={14} aria-hidden="true" />}
          {sim.running ? 'Pause' : 'Run'}
        </button>
        <div className="twin-speed" role="group" aria-label="Simulation speed">
          {SPEEDS.map((value) => (
            <button key={value} type="button" aria-pressed={sim.speed === value} className={sim.speed === value ? 'is-active' : ''} onClick={() => sim.setSpeed(value)}>{value}×</button>
          ))}
        </div>
      </div>
      <form className="twin-strip-group twin-demand" onSubmit={submit} noValidate>
        <label htmlFor="twin-demand-input">Demand</label>
        <input id="twin-demand-input" inputMode="decimal" value={demand} aria-invalid={Boolean(demandError)} aria-describedby={demandError ? 'twin-demand-error' : undefined} onChange={(event) => setDemand(event.target.value)} />
        <span className="twin-unit">MW</span>
        <button type="submit" className="twin-button" disabled={!can('set_load')}>Set</button>
        {demandError && <span id="twin-demand-error" className="twin-field-error" role="alert">{demandError}</span>}
      </form>
      <div className="twin-strip-group twin-strip-end">
        <button type="button" className="twin-button" onClick={onFaults}><Zap size={14} aria-hidden="true" />Faults</button>
        <button type="button" className="twin-button" onClick={onLog}><History size={14} aria-hidden="true" />Log</button>
        <a className="twin-button" href={operateHref}><SlidersHorizontal size={14} aria-hidden="true" />Operate</a>
      </div>
    </section>
  )
}

function UnitNow({ sim }: { sim: TwinSession }) {
  const values = unitNow(sim.state!, sim.summary)
  return (
    <section className="twin-card twin-now" aria-labelledby="twin-now-title">
      <h2 id="twin-now-title">Unit now</h2>
      <dl>
        {values.map((item) => (
          <div key={item.id} className={`is-${item.tone}`} data-testid={`now-${item.id}`}>
            <dt>{item.label}</dt>
            <dd>
              <span className="twin-now-value">{item.value}</span>
              {item.reference && <span className="twin-now-ref">{item.reference}</span>}
              <ToneMark tone={item.tone} />
            </dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

function ChecksTable({ decision }: { decision: Decision }) {
  return (
    <table className="twin-table">
      <thead><tr><th scope="col">Check</th><th scope="col">Result</th><th scope="col">Detail</th></tr></thead>
      <tbody>
        {decision.verdict.checks.map((check) => (
          <tr key={check.name}>
            <th scope="row">{CHECK_LABELS[check.name] ?? check.name}</th>
            <td className={check.passed ? '' : 'is-failed'}>{check.passed ? 'Pass' : 'Fail'}</td>
            <td>{check.detail || '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Candidates({ summary }: { summary: SupervisorSummary }) {
  const evaluation = summary.last_load_evaluation
  if (!evaluation) return null
  return (
    <details className="twin-disclosure">
      <summary>Load candidates at {formatClock(evaluation.t_s)} ({evaluation.candidates.length})</summary>
      <p className="twin-note">Band {evaluation.band_mw[0].toFixed(1)} to {evaluation.band_mw[1].toFixed(1)} MW; screening exhaust limit {kToC(evaluation.screen_exhaust_limit_k).toFixed(0)} °C. Now: {evaluation.current.heat_rate_kj_per_kwh.toFixed(0)} kJ/kWh.</p>
      <div className="twin-table-wrap">
        <table className="twin-table">
          <thead><tr><th scope="col">Load</th><th scope="col">IGV</th><th scope="col">Exhaust</th><th scope="col">Heat rate</th><th scope="col">Feasible</th></tr></thead>
          <tbody>
            {[...evaluation.candidates].sort((a, b) => a.heat_rate_kj_per_kwh - b.heat_rate_kj_per_kwh).map((c) => (
              <tr key={`${c.load_mw}-${c.igv}`}>
                <td>{c.load_mw.toFixed(1)} MW</td>
                <td>{c.igv === 'auto' ? 'auto' : `${(Number(c.igv) * 100).toFixed(0)} %`}</td>
                <td>{kToC(c.exhaust_k).toFixed(0)} °C</td>
                <td>{c.heat_rate_kj_per_kwh.toFixed(0)}</td>
                <td>{c.feasible ? 'yes' : 'no'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  )
}

function ActionCard({ sim, onLog }: { sim: TwinSession; onLog: () => void }) {
  const summary = sim.summary
  const rec = currentRecommendation(summary)
  const shown = displayedMode(sim.mode)
  return (
    <section className="twin-card twin-action" aria-labelledby="twin-action-title">
      <div className="twin-card-head">
        <h2 id="twin-action-title">Recommendation</h2>
        <ModeSwitch value={shown} pending={sim.mode.requested} onChange={(mode) => void sim.changeMode(mode)} disabled={!summary || sim.mode.requested !== null} />
      </div>
      {sim.mode.error && <p className="twin-field-error" role="alert">{sim.mode.error}</p>}
      {summary?.procedure.length ? <p className="twin-banner is-warning" role="status"><TriangleAlert size={14} aria-hidden="true" />Wash procedure running: {summary.procedure.join(' → ').replaceAll('_', ' ')}</p> : null}
      {!rec && (
        <div className="twin-empty" data-testid="no-recommendation">
          <p><strong>No recommendation.</strong> {summary?.mode === 'manual' ? 'Manual mode: the layer only watches.' : 'The layer is watching the unit.'}</p>
          <p className="twin-note">{summary ? MODE_HINTS[summary.mode] : ''}</p>
        </div>
      )}
      {rec && (
        <article className={`twin-rec is-${rec.tone}`} data-testid="recommendation" aria-live="polite">
          <div className="twin-rec-head">
            <span className={`twin-status is-${rec.tone}`}>{rec.tone === 'warning' && <TriangleAlert size={13} aria-hidden="true" />}{rec.statusLabel}</span>
            <span className="twin-rec-problem">{rec.title}</span>
            <time className="twin-rec-time">{formatClock(rec.decision.t_s)}</time>
          </div>
          <p className="twin-rec-summary">{rec.decision.summary}</p>
          {rec.gain && <p className="twin-rec-gain">Expected: {rec.gain}</p>}
          <p className={`twin-rec-guard ${rec.approved ? '' : 'is-failed'}`}>
            {rec.approved ? <Check size={14} aria-hidden="true" /> : <CircleAlert size={14} aria-hidden="true" />}
            {rec.approved ? 'Safety guard: all checks passed' : `Safety guard: ${rec.failedChecks.length} check${rec.failedChecks.length === 1 ? '' : 's'} failed`}
          </p>
          {!rec.approved && (
            <ul className="twin-failed-checks">
              {rec.failedChecks.map((check) => <li key={check.name}><strong>{check.label}</strong>{check.detail ? `: ${check.detail}` : ''}</li>)}
            </ul>
          )}
          {rec.open && (
            <div className="twin-rec-actions">
              <button type="button" className="twin-primary" disabled={sim.busy} onClick={() => void sim.decide(rec.decision.id, true)}><Check size={14} aria-hidden="true" />Accept</button>
              <button type="button" className="twin-button" disabled={sim.busy} onClick={() => void sim.decide(rec.decision.id, false)}><X size={14} aria-hidden="true" />Reject</button>
            </div>
          )}
          <details className="twin-disclosure">
            <summary>Guard checks ({rec.decision.verdict.checks.length})</summary>
            <ChecksTable decision={rec.decision} />
          </details>
        </article>
      )}
      {summary?.substitute_active && (
        <div className="twin-banner is-warning">
          <TriangleAlert size={14} aria-hidden="true" />
          <span>Temperature control runs on the model exhaust estimate.</span>
          <button type="button" className="twin-button" disabled={sim.busy} onClick={() => void sim.trustThermocouple()}>Thermocouple repaired</button>
        </div>
      )}
      {summary && <Candidates summary={summary} />}
      <button type="button" className="twin-link" onClick={onLog}>Decision log ({summary?.decisions_total ?? 0})</button>
    </section>
  )
}

function HealthList({ summary }: { summary: SupervisorSummary | null }) {
  const rows = rankComponents(summary)
  return (
    <section className="twin-card twin-health" aria-labelledby="twin-health-title">
      <h2 id="twin-health-title">Component health</h2>
      <p className="twin-note">Worst first. Only estimated quantities carry a value (± one standard deviation).</p>
      <ol className="twin-health-list">
        {rows.map((row) => (
          <li key={row.id} className={`is-${row.tone}`} data-testid={`health-${row.id}`}>
            <div className="twin-health-main">
              <span className="twin-health-label">{row.label}</span>
              <span className="twin-health-value">{row.value}</span>
            </div>
            <div className="twin-health-detail">
              <span>{row.detail}</span>
              <ToneMark tone={row.tone} />
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}

function LogSheet({ open, onClose, sim }: { open: boolean; onClose: () => void; sim: TwinSession }) {
  const [decisions, setDecisions] = useState<Decision[] | null>(null)
  const total = sim.summary?.decisions_total ?? 0
  useEffect(() => {
    if (!open || !sim.sessionId) return
    let active = true
    twinApi.decisions(sim.sessionId).then((log) => { if (active) setDecisions([...log.decisions].reverse()) }).catch(() => { if (active) setDecisions([]) })
    return () => { active = false }
  }, [open, sim.sessionId, total])
  return (
    <Sheet open={open} onClose={onClose} className="boundary-sheet twin-sheet" labelledBy="twin-log-title">
      <div className="boundary-sheet-heading">
        <div>
          <div className="page-context">Prescriptive layer</div>
          <h2 id="twin-log-title">Decision and event log</h2>
        </div>
        <button className="boundary-close" data-sheet-autofocus type="button" aria-label="Close log" onClick={onClose}><X size={17} aria-hidden="true" /></button>
      </div>
      <h3 className="twin-sheet-subhead">Decisions</h3>
      {decisions === null ? <p className="twin-note">Loading…</p> : decisions.length === 0 ? <p className="twin-note">No decisions yet.</p> : (
        <ol className="twin-decision-log">
          {decisions.map((d) => (
            <li key={d.id}>
              <details>
                <summary>
                  <time>{formatClock(d.t_s)}</time>
                  <span className="twin-decision-title">#{d.id} {PROBLEM_LABELS[d.problem] ?? d.problem}</span>
                  <span className={`twin-status is-${d.status === 'escalated' ? 'warning' : 'normal'}`}>{STATUS_LABELS[d.status] ?? d.status}</span>
                </summary>
                <p>{d.summary}</p>
                <p className="twin-note">{d.reason} · mode {d.mode}{d.resolved_by ? ` · by ${d.resolved_by}` : ''}</p>
                <ChecksTable decision={d} />
              </details>
            </li>
          ))}
        </ol>
      )}
      <h3 className="twin-sheet-subhead">Events</h3>
      {sim.log.length === 0 ? <p className="twin-note">No events yet.</p> : (
        <ol className="operate-log">
          {sim.log.map((entry) => (
            <li key={entry.id} className={`is-${entry.kind}`}><time>{formatClock(entry.t_s)}</time><span>{entry.text}</span></li>
          ))}
        </ol>
      )}
    </Sheet>
  )
}

export default function TwinConsole() {
  const { state: app } = useTurbineStore()
  const sim = useTwinSession()
  const reduceMotion = useReducedMotion()
  const [faultsOpen, setFaultsOpen] = useState(false)
  const [logOpen, setLogOpen] = useState(false)
  const state = sim.state
  const trip = state ? tripLabel(state) : null

  return (
    <div className="twin-page" id="route-outlet">
      {app.engineStatus === 'offline' && <EngineOfflineBanner />}
      {sim.error && <p className="operate-error" role="alert">{sim.error}</p>}
      {!state && !sim.resuming && <StartCard busy={sim.busy} onCreate={(mode) => void sim.create(mode)} />}
      {state && (
        <>
          <ControlStrip sim={sim} onFaults={() => setFaultsOpen(true)} onLog={() => setLogOpen(true)} />
          <div className="twin-grid">
            <section className={`twin-hero ${trip ? 'is-tripped' : ''}`} aria-labelledby="twin-hero-title">
              <h2 id="twin-hero-title" className="twin-sr">Live 3D twin</h2>
              <LiveTurbine
                speedPu={state.speed_pu}
                flame={state.flame}
                tripped={Boolean(trip)}
                exhaustK={state.exhaust_temperature_k}
                limitK={state.temperature_limit_k}
                callouts={stageCallouts(state, sim.summary)}
                reduceMotion={reduceMotion}
              />
              <div className="twin-hero-overlay">
                <span className="twin-hero-chip">{(state.speed_pu * 100).toFixed(0)} % speed</span>
                <span className="twin-hero-chip">{state.flame ? 'Flame on' : 'No flame'}</span>
                {reduceMotion && <span className="twin-hero-chip">Rotor motion off (reduced motion)</span>}
              </div>
              {trip && <div className="twin-trip-banner" role="alert" data-testid="trip-banner"><OctagonAlert size={18} aria-hidden="true" /><span>TRIPPED · {trip}</span></div>}
              <p className="twin-hero-note">Simulated unit · visual model, not to scale</p>
            </section>
            <div className="twin-side">
              <UnitNow sim={sim} />
              <ActionCard sim={sim} onLog={() => setLogOpen(true)} />
            </div>
            <TwinTrend samples={sim.samples} demands={sim.demands} />
            <HealthList summary={sim.summary} />
          </div>
          <Sheet open={faultsOpen} onClose={() => setFaultsOpen(false)} className="boundary-sheet twin-sheet twin-fault-sheet" labelledBy="twin-faults-title">
            <div className="boundary-sheet-heading">
              <div>
                <div className="page-context">Test the layer</div>
                <h2 id="twin-faults-title">Inject a fault</h2>
              </div>
              <button className="boundary-close" data-sheet-autofocus type="button" aria-label="Close faults" onClick={() => setFaultsOpen(false)}><X size={17} aria-hidden="true" /></button>
            </div>
            <FaultPanel state={state} busy={sim.busy} send={sim.send} />
          </Sheet>
          <LogSheet open={logOpen} onClose={() => setLogOpen(false)} sim={sim} />
        </>
      )}
    </div>
  )
}
