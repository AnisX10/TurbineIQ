import { useState } from 'react'
import type { FormEvent } from 'react'
import { Droplets, X } from 'lucide-react'
import { Field } from './Field'
import {
  CHANNELS,
  CHANNEL_ORDER,
  DEGRADATION_LABELS,
  DEGRADATION_LIMITS,
  FUEL_VALVE_LAG_RANGE,
  MAX_DEGRADATION_RATE,
  SENSOR_MODE_LABELS,
  activeFaults,
  buildDegradation,
  buildSensorFault,
  instrumentRows,
  isAllowed,
  parseBounded,
  sensorMagnitudeUnit,
} from './simLogic'
import type { SimChannel, SimDegradationKind, SimSensorMode, SimState } from './simTypes'

interface Props {
  state: SimState
  busy: boolean
  send: (command: string, params?: Record<string, unknown>) => Promise<boolean>
}

/** Inject and clear simulated faults, and show their ground truth next to the instruments. */
export function FaultPanel({ state, busy, send }: Props) {
  const [kind, setKind] = useState<SimDegradationKind>('compressor_fouling')
  const [severity, setSeverity] = useState('2')
  const [rate, setRate] = useState('0')
  const [channel, setChannel] = useState<SimChannel>('exhaust_temperature')
  const [mode, setMode] = useState<SimSensorMode>('bias')
  const [magnitude, setMagnitude] = useState('10')
  const [lag, setLag] = useState('2')
  const [errors, setErrors] = useState<{ degradation?: string; sensor?: string; valve?: string }>({})

  const can = (command: string) => isAllowed(state, command) && !busy
  const faults = activeFaults(state.injected_faults)
  const magnitudeUnit = sensorMagnitudeUnit(channel, mode)

  const injectDegradation = (event: FormEvent) => {
    event.preventDefault()
    const built = buildDegradation(kind, severity, rate)
    setErrors((e) => ({ ...e, degradation: 'error' in built ? built.error : undefined }))
    if ('params' in built) void send('inject_degradation', built.params)
  }
  const injectSensor = (event: FormEvent) => {
    event.preventDefault()
    const built = buildSensorFault(channel, mode, magnitude)
    setErrors((e) => ({ ...e, sensor: 'error' in built ? built.error : undefined }))
    if ('params' in built) void send('inject_sensor_fault', built.params)
  }
  const slowValve = (event: FormEvent) => {
    event.preventDefault()
    const [lo, hi] = FUEL_VALVE_LAG_RANGE
    const value = parseBounded(lag, lo, hi)
    setErrors((e) => ({ ...e, valve: value === null ? `Enter ${lo} to ${hi} s.` : undefined }))
    if (value !== null) void send('set_fuel_valve_lag', { tau_s: value })
  }

  return (
    <section className="operate-card" aria-labelledby="operate-faults-title">
      <h2 id="operate-faults-title">Fault injection</h2>
      <p className="operate-note">
        Injected faults are the ground truth for testing diagnostics. Degradation changes the plant; a sensor fault changes only what
        the instrument reports, except the exhaust thermocouple, which the temperature control and protection also use. A fault acts
        from the next simulation step. Magnitudes are illustrative, not OEM data.
      </p>

      <div className="operate-forms">
        <form onSubmit={injectDegradation} noValidate aria-label="Gas-path degradation">
          <Field label="Degradation">
            {({ id }) => (
              <select id={id} value={kind} onChange={(e) => setKind(e.target.value as SimDegradationKind)}>
                {(Object.keys(DEGRADATION_LABELS) as SimDegradationKind[]).map((k) => <option key={k} value={k}>{DEGRADATION_LABELS[k]}</option>)}
              </select>
            )}
          </Field>
          <Field label="Severity (%)" hint={`0 to ${DEGRADATION_LIMITS[kind]}`} error={errors.degradation}>
            {({ id, describedBy }) => <input id={id} aria-describedby={describedBy} aria-invalid={Boolean(errors.degradation)} inputMode="decimal" value={severity} onChange={(e) => setSeverity(e.target.value)} />}
          </Field>
          <Field label="Growth (%/h)" hint={`0 to ${MAX_DEGRADATION_RATE}; grows only while air flows`}>
            {({ id, describedBy }) => <input id={id} aria-describedby={describedBy} inputMode="decimal" value={rate} onChange={(e) => setRate(e.target.value)} />}
          </Field>
          <button type="submit" disabled={!can('inject_degradation')}>Inject degradation</button>
          <p className="operate-note">An offline wash removes the fouling but not its growth rate. Only at standstill.</p>
          <button type="button" disabled={!can('wash_compressor')} onClick={() => void send('wash_compressor')}>
            <Droplets size={15} aria-hidden="true" /><span>Offline compressor wash</span>
          </button>
        </form>

        <form onSubmit={injectSensor} noValidate aria-label="Sensor fault">
          <Field label="Sensor">
            {({ id }) => (
              <select id={id} value={channel} onChange={(e) => setChannel(e.target.value as SimChannel)}>
                {CHANNEL_ORDER.map((c) => <option key={c} value={c}>{CHANNELS[c].label}</option>)}
              </select>
            )}
          </Field>
          <Field label="Fault mode">
            {({ id }) => (
              <select id={id} value={mode} onChange={(e) => setMode(e.target.value as SimSensorMode)}>
                {(Object.keys(SENSOR_MODE_LABELS) as SimSensorMode[]).map((m) => <option key={m} value={m}>{SENSOR_MODE_LABELS[m]}</option>)}
              </select>
            )}
          </Field>
          <Field label={magnitudeUnit ? `Magnitude (${magnitudeUnit})` : 'Magnitude'} hint={magnitudeUnit ? `Within ±${CHANNELS[channel].limit}` : 'Freezes at the current reading'} error={errors.sensor}>
            {({ id, describedBy }) => <input id={id} aria-describedby={describedBy} aria-invalid={Boolean(errors.sensor)} inputMode="decimal" value={magnitude} disabled={!magnitudeUnit} onChange={(e) => setMagnitude(e.target.value)} />}
          </Field>
          <button type="submit" disabled={!can('inject_sensor_fault')}>Inject sensor fault</button>
        </form>

        <form onSubmit={slowValve} noValidate aria-label="Fuel valve">
          <Field label="Fuel valve lag (s)" hint={`${FUEL_VALVE_LAG_RANGE[0]} to ${FUEL_VALVE_LAG_RANGE[1]}; healthy valve 0.05`} error={errors.valve}>
            {({ id, describedBy }) => <input id={id} aria-describedby={describedBy} aria-invalid={Boolean(errors.valve)} inputMode="decimal" value={lag} onChange={(e) => setLag(e.target.value)} />}
          </Field>
          <button type="submit" disabled={!can('set_fuel_valve_lag')}>Slow the fuel valve</button>
        </form>
      </div>

      <div className="operate-fault-grid">
        <div>
          <h3>Active faults</h3>
          {faults.length === 0 ? <p className="operate-note" data-testid="no-faults">None. The unit is healthy.</p> : (
            <>
              <ul className="operate-fault-list" data-testid="active-faults">
                {faults.map((fault) => (
                  <li key={fault.target}>
                    <span><strong>{fault.label}</strong> {fault.detail}</span>
                    <button type="button" aria-label={`Clear ${fault.label}`} disabled={!can('clear_fault')} onClick={() => void send('clear_fault', { target: fault.target })}>
                      <X size={14} aria-hidden="true" /><span>Clear</span>
                    </button>
                  </li>
                ))}
              </ul>
              <button type="button" className="operate-quiet" disabled={!can('clear_fault')} onClick={() => void send('clear_fault', { target: 'all' })}>Clear all faults</button>
            </>
          )}
        </div>
        <div className="operate-instruments">
          <table>
            <caption>Instruments: true value and reading</caption>
            <thead><tr><th scope="col">Channel</th><th scope="col">True</th><th scope="col">Reading</th><th scope="col">Unit</th></tr></thead>
            <tbody>
              {instrumentRows(state).map((row) => (
                <tr key={row.channel}>
                  <th scope="row">{row.label}{state.injected_faults.sensors[row.channel] ? <span className="operate-fault-flag"> (fault)</span> : null}</th>
                  <td data-testid={`truth-${row.channel}`}>{row.truth.toFixed(row.digits)}</td>
                  <td data-testid={`reading-${row.channel}`}>{row.measured.toFixed(row.digits)}</td>
                  <td>{row.unit}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}
