import type { SimChannel, SimDegradationKind, SimInjectedFaults, SimSensorMode, SimState } from './simTypes'

export const STATE_LABELS: Record<string, string> = {
  standstill: 'Standstill',
  crank: 'Cranking',
  purge: 'Purging',
  ignition: 'Ignition',
  warmup: 'Warm-up',
  accelerate: 'Accelerating',
  full_speed_no_load: 'Full speed, no load',
  loaded: 'Loaded',
  unloading: 'Unloading',
  cooldown: 'Cool-down',
  coastdown: 'Coasting down',
  tripped: 'Tripped',
}

export const TRIP_LABELS: Record<string, string> = {
  manual_emergency_trip: 'Manual emergency trip',
  overspeed: 'Overspeed',
  underspeed: 'Underspeed',
  exhaust_over_temperature: 'Exhaust over-temperature',
}

export const LIMITER_LABELS: Record<string, string> = {
  governor: 'Governor (load / speed)',
  temperature: 'Exhaust-temperature limit',
  acceleration: 'Acceleration limit',
  ignition_schedule: 'Ignition schedule',
  fuel_off: 'Fuel off',
  none: 'None',
}

export type StateTone = 'neutral' | 'positive' | 'warning' | 'negative'

export function stateTone(state: string): StateTone {
  if (state === 'tripped') return 'negative'
  if (state === 'loaded') return 'positive'
  if (state === 'standstill') return 'neutral'
  return 'warning'
}

export function isAllowed(state: SimState | null, command: string): boolean {
  return Boolean(state?.available_commands.includes(command))
}

/** Parse a form field to a number inside [min, max], or null when it is not valid. */
export function parseBounded(text: string, min: number, max: number): number | null {
  if (text.trim() === '') return null
  const value = Number(text)
  return Number.isFinite(value) && value >= min && value <= max ? value : null
}

/** Append new samples, drop any already held (by step), and keep the most recent `max`. */
export function mergeSamples(previous: SimState[], incoming: SimState[], max = 600): SimState[] {
  const lastStep = previous.length ? previous[previous.length - 1].step : -1
  const fresh = incoming.filter((sample) => sample.step > lastStep)
  return [...previous, ...fresh].slice(-max)
}

export function formatSimTime(seconds: number): string {
  const whole = Math.floor(seconds)
  const h = Math.floor(whole / 3600)
  const m = Math.floor((whole % 3600) / 60)
  const s = whole % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`
}

export function commandSummary(command: string, params: Record<string, unknown>): string {
  const entries = Object.entries(params).filter(([, value]) => value !== null && value !== undefined)
  const detail = entries.map(([key, value]) => `${key.replaceAll('_', ' ')} ${String(value)}`).join(', ')
  return detail ? `${command.replaceAll('_', ' ')} (${detail})` : command.replaceAll('_', ' ')
}

// ---------------------------------------------------------------- fault injection
// The server validates every fault command; these mirror its limits
// (turbineiq.simulation.faults) only so the form can explain a bad value before sending.


export const DEGRADATION_LABELS: Record<SimDegradationKind, string> = {
  compressor_fouling: 'Compressor fouling',
  turbine_erosion: 'Turbine erosion',
}
export const DEGRADATION_LIMITS: Record<SimDegradationKind, number> = { compressor_fouling: 10, turbine_erosion: 5 }
export const MAX_DEGRADATION_RATE = 10
export const FUEL_VALVE_LAG_RANGE = [0.05, 5] as const

export const CHANNELS: Record<SimChannel, { label: string; unit: string; limit: number; digits: number }> = {
  electrical_power: { label: 'Electrical power', unit: 'MW', limit: 10, digits: 2 },
  exhaust_temperature: { label: 'Exhaust temperature', unit: 'K', limit: 100, digits: 1 },
  speed: { label: 'Speed', unit: 'pu', limit: 0.05, digits: 4 },
  compressor_discharge_temperature: { label: 'Compressor discharge temperature', unit: 'K', limit: 50, digits: 1 },
  compressor_discharge_pressure: { label: 'Compressor discharge pressure', unit: 'kPa', limit: 100, digits: 1 },
  fuel_flow: { label: 'Fuel flow', unit: 'kg/s', limit: 0.5, digits: 3 },
}
export const CHANNEL_ORDER = Object.keys(CHANNELS) as SimChannel[]

export const SENSOR_MODE_LABELS: Record<SimSensorMode, string> = {
  bias: 'Bias (constant offset)',
  drift: 'Drift (offset per hour)',
  stuck: 'Stuck (frozen reading)',
  noise: 'Extra noise (sigma)',
}

/** Unit of the magnitude a sensor fault takes, or null when the mode takes none. */
export function sensorMagnitudeUnit(channel: SimChannel, mode: SimSensorMode): string | null {
  if (mode === 'stuck') return null
  return CHANNELS[channel].unit + (mode === 'drift' ? '/h' : '')
}

export type Built = { params: Record<string, unknown> } | { error: string }

export function buildDegradation(kind: SimDegradationKind, severityText: string, rateText: string): Built {
  const limit = DEGRADATION_LIMITS[kind]
  const severity = parseBounded(severityText, 0, limit)
  if (severity === null) return { error: `Enter a severity from 0 to ${limit} %.` }
  const rate = rateText.trim() === '' ? 0 : parseBounded(rateText, 0, MAX_DEGRADATION_RATE)
  if (rate === null) return { error: `Enter a growth rate from 0 to ${MAX_DEGRADATION_RATE} %/h.` }
  if (severity === 0 && rate === 0) return { error: 'Give a severity or a growth rate above zero.' }
  return { params: { kind, severity_pct: severity, rate_pct_per_h: rate } }
}

export function buildSensorFault(channel: SimChannel, mode: SimSensorMode, magnitudeText: string): Built {
  if (mode === 'stuck') return { params: { channel, mode } }
  const { limit, unit } = CHANNELS[channel]
  const value = parseBounded(magnitudeText, -limit, limit)
  const shown = `${unit}${mode === 'drift' ? '/h' : ''}`
  if (mode === 'noise') {
    if (value === null || value <= 0) return { error: `Enter a sigma above 0 and at most ${limit} ${shown}.` }
  } else if (value === null || value === 0) {
    return { error: `Enter a non-zero value within ±${limit} ${shown}.` }
  }
  return { params: { channel, mode, magnitude: value } }
}

export interface ActiveFault { target: string; label: string; detail: string }

function signed(value: number): string {
  return value > 0 ? `+${value}` : String(value)
}

/** The injected faults as one row each, with the clear_fault target that removes it. */
export function activeFaults(faults: SimInjectedFaults | undefined): ActiveFault[] {
  if (!faults) return []
  const rows: ActiveFault[] = []
  for (const kind of Object.keys(DEGRADATION_LABELS) as SimDegradationKind[]) {
    const item = faults.degradation[kind]
    if (!item) continue
    const growth = item.rate_pct_per_h > 0 ? `, growing ${item.rate_pct_per_h} %/h` : ''
    rows.push({ target: kind, label: DEGRADATION_LABELS[kind], detail: `${item.severity_pct.toFixed(2)} %${growth}` })
  }
  for (const channel of CHANNEL_ORDER) {
    const fault = faults.sensors[channel]
    if (!fault) continue
    const { label, digits } = CHANNELS[channel]
    const detail = fault.mode === 'stuck'
      ? `stuck at ${fault.stuck_value === undefined ? '?' : fault.stuck_value.toFixed(digits)} ${CHANNELS[channel].unit}`
      : `${fault.mode} ${fault.mode === 'noise' ? fault.magnitude : signed(fault.magnitude ?? 0)} ${fault.unit}`
    rows.push({ target: channel, label: `${label} sensor`, detail })
  }
  if (faults.fuel_valve_lag_s !== null) {
    rows.push({ target: 'fuel_valve', label: 'Slow fuel valve', detail: `lag ${faults.fuel_valve_lag_s} s` })
  }
  return rows
}

export interface InstrumentRow { channel: SimChannel; label: string; unit: string; truth: number; measured: number; digits: number }

/** True value next to the instrument reading for each channel (the reading includes noise). */
export function instrumentRows(state: SimState): InstrumentRow[] {
  const m = state.measured
  const pairs: Record<SimChannel, [number, number]> = {
    electrical_power: [state.electrical_power_mw, m.electrical_power_mw],
    exhaust_temperature: [state.exhaust_temperature_k, m.exhaust_temperature_k],
    speed: [state.speed_pu, m.speed_pu],
    compressor_discharge_temperature: [state.compressor_discharge_temperature_k, m.compressor_discharge_temperature_k],
    compressor_discharge_pressure: [state.compressor_discharge_pressure_kpa, m.compressor_discharge_pressure_kpa],
    fuel_flow: [state.fuel_flow_kg_s, m.fuel_flow_kg_s],
  }
  return CHANNEL_ORDER.map((channel) => ({
    channel,
    label: CHANNELS[channel].label,
    unit: CHANNELS[channel].unit,
    truth: pairs[channel][0],
    measured: pairs[channel][1],
    digits: CHANNELS[channel].digits,
  }))
}
