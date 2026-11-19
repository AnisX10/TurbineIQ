import { useState } from 'react'
import type { FormEvent } from 'react'
import { OctagonAlert, Pause, Play, Power, RotateCcw } from 'lucide-react'
import { useTurbineStore } from '../../app/useTurbineStore'
import { EngineOfflineBanner } from '../../components/ui/EngineOfflineBanner'
import { FaultPanel } from './FaultPanel'
import { Field } from './Field'
import { Trend } from './Trend'
import { useSimSession } from './useSimSession'
import {
  LIMITER_LABELS,
  STATE_LABELS,
  TRIP_LABELS,
  formatSimTime,
  isAllowed,
  parseBounded,
  stateTone,
} from './simLogic'
import type { SimGrid } from './simTypes'
import './Operate.css'

const SPEEDS = [1, 10, 60] as const
const MAX_LOAD_MW = 47

function CreateForm({ busy, onCreate }: { busy: boolean; onCreate: (config: { seed: number; ambient_temperature_c: number; grid: SimGrid }) => void }) {
  const [seed, setSeed] = useState('1')
  const [ambient, setAmbient] = useState('15')
  const [grid, setGrid] = useState<SimGrid>('infinite_bus')
  const [errors, setErrors] = useState<{ seed?: string; ambient?: string }>({})
  const submit = (event: FormEvent) => {
    event.preventDefault()
    const seedValue = parseBounded(seed, 0, 2147483647)
    const ambientValue = parseBounded(ambient, -40, 55)
    const next = {
      ...(seedValue === null || !Number.isInteger(seedValue) ? { seed: 'Enter a whole number from 0 to 2147483647.' } : {}),
      ...(ambientValue === null ? { ambient: 'Enter a temperature from -40 to 55 °C.' } : {}),
    }
    setErrors(next)
    if (Object.keys(next).length || seedValue === null || ambientValue === null) return
    onCreate({ seed: seedValue, ambient_temperature_c: ambientValue, grid })
  }
  return (
    <form className="operate-card operate-create" onSubmit={submit} noValidate>
      <h2>Create a simulated unit</h2>
      <p className="operate-note">A model of a GE 6B.03-class unit, held in memory. It is not connected to any real machine.</p>
      <div className="operate-form-row">
        <Field label="Seed" hint="Fixes measurement noise" error={errors.seed}>
          {({ id, describedBy }) => <input id={id} aria-describedby={describedBy} aria-invalid={Boolean(errors.seed)} inputMode="numeric" value={seed} onChange={(e) => setSeed(e.target.value)} />}
        </Field>
        <Field label="Ambient (°C)" error={errors.ambient}>
          {({ id, describedBy }) => <input id={id} aria-describedby={describedBy} aria-invalid={Boolean(errors.ambient)} inputMode="decimal" value={ambient} onChange={(e) => setAmbient(e.target.value)} />}
        </Field>
        <Field label="Grid">
          {({ id }) => (
            <select id={id} value={grid} onChange={(e) => setGrid(e.target.value as SimGrid)}>
              <option value="infinite_bus">Infinite bus (grid sets speed)</option>
              <option value="island">Island (unit sets frequency)</option>
            </select>
          )}
        </Field>
      </div>
      <button className="operate-primary" type="submit" disabled={busy}>Create unit</button>
    </form>
  )
}

export default function Operate() {
  const { state: app } = useTurbineStore()
  const sim = useSimSession()
  const { state } = sim
  const [load, setLoad] = useState('30')
  const [ramp, setRamp] = useState('10')
  const [igvMode, setIgvMode] = useState<'auto' | 'manual'>('auto')
  const [igvPosition, setIgvPosition] = useState('100')
  const [ambient, setAmbient] = useState('15')
  const [freq, setFreq] = useState('50')
  const [islandLoad, setIslandLoad] = useState('20')
  const [errors, setErrors] = useState<Record<string, string>>({})

  const setError = (key: string, message: string | null) =>
    setErrors((previous) => {
      const next = { ...previous }
      if (message) next[key] = message
      else delete next[key]
      return next
    })

  const applyLoad = (event: FormEvent) => {
    event.preventDefault()
    const mw = parseBounded(load, 0, MAX_LOAD_MW)
    const rate = parseBounded(ramp, 0.1, 120)
    setError('load', mw === null ? `Enter 0 to ${MAX_LOAD_MW} MW.` : null)
    setError('ramp', rate === null ? 'Enter 0.1 to 120 MW/min.' : null)
    if (mw !== null && rate !== null) void sim.send('set_load', { mw, ramp_mw_per_min: rate })
  }
  const applyIgv = (event: FormEvent) => {
    event.preventDefault()
    const position = parseBounded(igvPosition, 0, 100)
    setError('igv', igvMode === 'manual' && position === null ? 'Enter 0 to 100 %.' : null)
    if (igvMode === 'auto') void sim.send('set_igv', { mode: 'auto' })
    else if (position !== null) void sim.send('set_igv', { mode: 'manual', position: position / 100 })
  }
  const applyAmbient = (event: FormEvent) => {
    event.preventDefault()
    const value = parseBounded(ambient, -40, 55)
    setError('ambient', value === null ? 'Enter -40 to 55 °C.' : null)
    if (value !== null) void sim.send('set_ambient', { temperature_c: value })
  }
  const applyGrid = (event: FormEvent) => {
    event.preventDefault()
    if (state?.grid === 'island') {
      const mw = parseBounded(islandLoad, 0, MAX_LOAD_MW)
      setError('grid', mw === null ? `Enter 0 to ${MAX_LOAD_MW} MW.` : null)
      if (mw !== null) void sim.send('set_island_load', { mw })
    } else {
      const hz = parseBounded(freq, 47.5, 52.5)
      setError('grid', hz === null ? 'Enter 47.5 to 52.5 Hz.' : null)
      if (hz !== null) void sim.send('set_grid_frequency', { hz })
    }
  }

  const can = (command: string) => isAllowed(state, command) && !sim.busy
  const tone = state ? stateTone(state.state) : 'neutral'
  const tripLabel = state?.trip_cause ? TRIP_LABELS[state.trip_cause] ?? state.trip_cause : null

  return (
    <div className="operate-page" id="route-outlet">
      {app.engineStatus === 'offline' && <EngineOfflineBanner />}
      <p className="operate-boundary">
        Simulated plant: Rowen-type dynamics on the calibrated cycle model. Time constants, start-up timings and
        protection thresholds are illustrative, not 6B.03 data. Nothing here is connected to a real machine.
      </p>

      {!state && <CreateForm busy={sim.busy} onCreate={(config) => void sim.create(config)} />}
      {sim.error && <p className="operate-error" role="alert">{sim.error}</p>}

      {state && (
        <>
          <section className="operate-card" aria-labelledby="operate-status-title">
            <div className="operate-status-head">
              <h2 id="operate-status-title">Unit status</h2>
              <span className={`operate-pill is-${tone}`} data-testid="unit-state">{STATE_LABELS[state.state] ?? state.state}</span>
              <span className="operate-clock" aria-label="Simulated time">{formatSimTime(state.t_s)}</span>
            </div>
            <p className="operate-live" role="status" aria-live="polite">
              {tripLabel ? `Unit tripped: ${tripLabel}.` : `${STATE_LABELS[state.state] ?? state.state}.`}
            </p>
            <dl className="operate-readouts">
              <div><dt>Electrical power</dt><dd data-testid="power">{state.electrical_power_mw.toFixed(1)} MW</dd></div>
              <div><dt>Speed</dt><dd>{state.speed_hz_equivalent.toFixed(2)} Hz equiv. <small>({(state.speed_pu * 100).toFixed(1)} %)</small></dd></div>
              <div><dt>Exhaust temperature</dt><dd>{state.exhaust_temperature_c.toFixed(0)} °C <small>limit {(state.temperature_limit_k - 273.15).toFixed(0)}</small></dd></div>
              <div><dt>Fuel flow</dt><dd>{state.fuel_flow_kg_s.toFixed(2)} kg/s</dd></div>
              <div><dt>Heat rate</dt><dd>{state.heat_rate_kj_per_kwh === null ? '—' : `${state.heat_rate_kj_per_kwh.toFixed(0)} kJ/kWh`}</dd></div>
              <div><dt>Breaker</dt><dd>{state.breaker_closed ? 'Closed' : 'Open'}</dd></div>
              <div><dt>Fuel limited by</dt><dd>{LIMITER_LABELS[state.limiter] ?? state.limiter}</dd></div>
              <div><dt>IGV</dt><dd>{(state.igv_position * 100).toFixed(0)} % ({state.igv_mode})</dd></div>
              <div><dt>Load reference</dt><dd>{state.load_reference_mw.toFixed(1)} → {state.load_setpoint_mw.toFixed(1)} MW</dd></div>
              <div><dt>Ambient</dt><dd>{state.ambient_temperature_c.toFixed(1)} °C</dd></div>
            </dl>
            <div className="operate-run">
              <button className="operate-primary" type="button" onClick={() => sim.setRunning(!sim.running)} aria-pressed={sim.running}>
                {sim.running ? <Pause size={15} aria-hidden="true" /> : <Play size={15} aria-hidden="true" />}
                <span>{sim.running ? 'Pause' : 'Run'}</span>
              </button>
              <div className="operate-speed" role="group" aria-label="Simulation speed">
                {SPEEDS.map((value) => (
                  <button key={value} type="button" aria-pressed={sim.speed === value} className={sim.speed === value ? 'is-active' : ''} onClick={() => sim.setSpeed(value)}>{value}×</button>
                ))}
              </div>
              <button className="operate-quiet" type="button" onClick={() => { sim.setRunning(false); void sim.create({ seed: 1, ambient_temperature_c: state.ambient_temperature_c, grid: state.grid }) }} disabled={sim.busy}>
                <RotateCcw size={14} aria-hidden="true" /><span>New unit</span>
              </button>
            </div>
          </section>

          <section className="operate-card" aria-labelledby="operate-commands-title">
            <h2 id="operate-commands-title">Commands</h2>
            <div className="operate-commands">
              <button type="button" disabled={!can('start')} onClick={() => void sim.send('start')}><Power size={15} aria-hidden="true" /><span>Start</span></button>
              <button type="button" disabled={!can('stop')} onClick={() => void sim.send('stop')}><span>Normal stop</span></button>
              <button type="button" disabled={!can('open_breaker')} onClick={() => void sim.send('open_breaker')}><span>Reject load (open breaker)</span></button>
              <button type="button" disabled={!can('close_breaker')} onClick={() => void sim.send('close_breaker')}><span>Close breaker</span></button>
              <button type="button" disabled={!can('reset')} onClick={() => void sim.send('reset')}><span>Reset trip</span></button>
              <button type="button" className="operate-danger" disabled={!can('trip')} onClick={() => void sim.send('trip')}><OctagonAlert size={15} aria-hidden="true" /><span>Emergency trip</span></button>
            </div>
            <div className="operate-forms">
              <form onSubmit={applyLoad} noValidate aria-label="Load setpoint">
                <Field label="Load setpoint (MW)" error={errors.load}>
                  {({ id, describedBy }) => <input id={id} aria-describedby={describedBy} aria-invalid={Boolean(errors.load)} inputMode="decimal" value={load} onChange={(e) => setLoad(e.target.value)} />}
                </Field>
                <Field label="Ramp (MW/min)" error={errors.ramp}>
                  {({ id, describedBy }) => <input id={id} aria-describedby={describedBy} aria-invalid={Boolean(errors.ramp)} inputMode="decimal" value={ramp} onChange={(e) => setRamp(e.target.value)} />}
                </Field>
                <button type="submit" disabled={!can('set_load')}>Apply load</button>
              </form>
              <form onSubmit={applyIgv} noValidate aria-label="Inlet guide vanes">
                <Field label="IGV mode">
                  {({ id }) => <select id={id} value={igvMode} onChange={(e) => setIgvMode(e.target.value as 'auto' | 'manual')}><option value="auto">Auto schedule</option><option value="manual">Manual</option></select>}
                </Field>
                <Field label="IGV position (%)" error={errors.igv}>
                  {({ id, describedBy }) => <input id={id} aria-describedby={describedBy} aria-invalid={Boolean(errors.igv)} inputMode="decimal" value={igvPosition} disabled={igvMode === 'auto'} onChange={(e) => setIgvPosition(e.target.value)} />}
                </Field>
                <button type="submit" disabled={!can('set_igv')}>Apply IGV</button>
              </form>
              <form onSubmit={applyAmbient} noValidate aria-label="Ambient temperature">
                <Field label="Ambient (°C)" error={errors.ambient}>
                  {({ id, describedBy }) => <input id={id} aria-describedby={describedBy} aria-invalid={Boolean(errors.ambient)} inputMode="decimal" value={ambient} onChange={(e) => setAmbient(e.target.value)} />}
                </Field>
                <button type="submit" disabled={!can('set_ambient')}>Apply ambient</button>
              </form>
              <form onSubmit={applyGrid} noValidate aria-label="Grid">
                {state.grid === 'island' ? (
                  <Field label="Island load (MW)" error={errors.grid}>
                    {({ id, describedBy }) => <input id={id} aria-describedby={describedBy} aria-invalid={Boolean(errors.grid)} inputMode="decimal" value={islandLoad} onChange={(e) => setIslandLoad(e.target.value)} />}
                  </Field>
                ) : (
                  <Field label="Grid frequency (Hz)" error={errors.grid}>
                    {({ id, describedBy }) => <input id={id} aria-describedby={describedBy} aria-invalid={Boolean(errors.grid)} inputMode="decimal" value={freq} onChange={(e) => setFreq(e.target.value)} />}
                  </Field>
                )}
                <button type="submit" disabled={!can(state.grid === 'island' ? 'set_island_load' : 'set_grid_frequency')}>{state.grid === 'island' ? 'Apply island load' : 'Apply frequency'}</button>
              </form>
            </div>
          </section>

          <FaultPanel state={state} busy={sim.busy} send={sim.send} />

          <section className="operate-card" aria-labelledby="operate-trends-title">
            <h2 id="operate-trends-title">Trends</h2>
            <div className="operate-trends">
              <Trend title="Electrical power" unit="MW" samples={sim.samples} pick={(s) => s.electrical_power_mw} />
              <Trend title="Speed" unit="Hz equiv." samples={sim.samples} pick={(s) => s.speed_hz_equivalent} digits={2} />
              <Trend title="Exhaust temperature" unit="°C" samples={sim.samples} pick={(s) => s.exhaust_temperature_c} digits={0} refLine={{ value: state.temperature_limit_k - 273.15, label: 'limit' }} />
              <Trend title="Fuel flow" unit="kg/s" samples={sim.samples} pick={(s) => s.fuel_flow_kg_s} digits={2} />
            </div>
          </section>

          <section className="operate-card" aria-labelledby="operate-log-title">
            <h2 id="operate-log-title">Event log</h2>
            {sim.log.length === 0 ? <p className="operate-note">No events yet.</p> : (
              <ol className="operate-log">
                {sim.log.map((entry) => (
                  <li key={entry.id} className={`is-${entry.kind}`}><time>{formatSimTime(entry.t_s)}</time><span>{entry.text}</span></li>
                ))}
              </ol>
            )}
          </section>
        </>
      )}
    </div>
  )
}
