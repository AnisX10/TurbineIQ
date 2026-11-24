/**
 * Pure logic of the live twin console: formatting, the component-health ranking, the
 * recommendation shown on the action card, the mode switch and the values that drive the
 * 3D stage. Nothing here invents a score: every row shows an estimate the supervisor made,
 * or says plainly that the part is not monitored.
 */
import type { SimState } from '../operate/simTypes'
import { STATE_LABELS, TRIP_LABELS } from '../operate/simLogic'
import type { Decision, HealthDeltas, SupervisorMode, SupervisorSummary } from './supervisorTypes'

export type Tone = 'normal' | 'warning' | 'alarm' | 'inactive'

export const MODE_LABELS: Record<SupervisorMode, string> = {
  manual: 'Manual',
  advisory: 'Advisory',
  autonomous: 'Autonomous',
}

export const MODE_HINTS: Record<SupervisorMode, string> = {
  manual: 'The layer estimates and watches; it proposes nothing.',
  advisory: 'Every recommendation waits for you.',
  autonomous: 'Guard-approved actions apply at once; the rest come to you.',
}

export const PROBLEM_LABELS: Record<string, string> = {
  load_setpoint: 'Load and IGV setpoint',
  compressor_wash: 'Compressor wash',
  exhaust_feedback: 'Exhaust temperature feedback',
}

export const STATUS_LABELS: Record<string, string> = {
  applied: 'Applied by the layer',
  pending: 'Waiting for you',
  escalated: 'Escalated to you',
  accepted: 'Accepted',
  rejected: 'Rejected',
  expired: 'Expired',
  superseded: 'Superseded',
}

export const CHECK_LABELS: Record<string, string> = {
  unit_loaded: 'Unit loaded',
  estimator_ready: 'Health estimator ready',
  health_converged: 'Health estimate converged',
  model_mismatch: 'Twin agrees with the plant',
  exhaust_reading_trusted: 'Exhaust reading trusted',
  exhaust_feedback_valid: 'Exhaust feedback valid',
  setpoint_step: 'Setpoint step size',
  ramp_rate: 'Ramp rate',
  action_interval: 'Time since last action',
  no_trip: 'No trip in forward run',
  peak_exhaust: 'Peak exhaust in forward run',
  settled_exhaust: 'Settled exhaust in forward run',
  speed_band: 'Speed band in forward run',
  meets_demand: 'Meets demand',
  model_exhaust_available: 'Model exhaust estimate available',
  shutdown_allowed: 'Shutdown allowed',
}

// ------------------------------------------------------------------ formatting

export const DASH = '—'

export function kToC(k: number): number {
  return k - 273.15
}

export function formatNumber(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined || !Number.isFinite(value) ? DASH : value.toFixed(digits)
}

/** A signed health delta in percent with its one-sigma uncertainty, e.g. "-1.20 % ± 0.05". */
export function formatDelta(delta: number, std: number | null | undefined): string {
  const pct = delta * 100
  const sign = pct > 0.0049 ? '+' : pct < -0.0049 ? '-' : ''
  const body = `${sign}${Math.abs(pct).toFixed(2)} %`
  return std === null || std === undefined || !Number.isFinite(std) ? body : `${body} ± ${(std * 100).toFixed(2)}`
}

export function formatClock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds))
  const h = Math.floor(whole / 3600)
  const m = Math.floor((whole % 3600) / 60)
  const s = whole % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`
}

// ------------------------------------------------------------------ component health

/**
 * Loss (percentage points below the clean engine) at which a health row turns to warning
 * and to alarm. Illustrative console thresholds, not OEM limits.
 */
export const HEALTH_WARNING_PCT = 1.0
export const HEALTH_ALARM_PCT = 2.5

export interface HealthRow {
  id: string
  label: string
  value: string
  detail: string
  tone: Tone
  /** What the row is based on: an estimate, a check, or nothing. */
  basis: 'estimate' | 'check' | 'not_monitored' | 'waiting'
  /** Larger is worse; used for ranking. */
  severity: number
}

const ESTIMATED: Array<{ id: keyof HealthDeltas; label: string; meaning: string }> = [
  { id: 'compressor_flow', label: 'Compressor flow capacity', meaning: 'fouling lowers it' },
  { id: 'compressor_efficiency', label: 'Compressor efficiency', meaning: 'fouling and erosion lower it' },
  { id: 'turbine_efficiency', label: 'Turbine efficiency', meaning: 'erosion lowers it' },
]

function toneForLoss(lossPct: number): Tone {
  if (lossPct >= HEALTH_ALARM_PCT) return 'alarm'
  if (lossPct >= HEALTH_WARNING_PCT) return 'warning'
  return 'normal'
}

const TONE_RANK: Record<Tone, number> = { alarm: 3, warning: 2, normal: 1, inactive: 0 }

/** Component rows, worst first. Only what the supervisor estimates gets a value. */
export function rankComponents(summary: SupervisorSummary | null): HealthRow[] {
  const status = summary?.status ?? null
  const ready = Boolean(status && status.estimator_updates > 0)
  const rows: HealthRow[] = ESTIMATED.map(({ id, label, meaning }) => {
    if (!status || !ready) {
      return { id, label, value: DASH, detail: 'Estimated once the unit runs steady at load', tone: 'inactive', basis: 'waiting', severity: -1 }
    }
    const delta = status.health[id]
    const loss = Math.max(0, -delta * 100)
    return {
      id,
      label,
      value: formatDelta(delta, status.health_std[id]),
      detail: `Estimated against the clean engine; ${meaning}`,
      tone: toneForLoss(loss),
      basis: 'estimate',
      severity: loss,
    }
  })
  rows.push(thermocoupleRow(summary))
  rows.push(
    { id: 'fuel_valve', label: 'Fuel valve', value: 'Not monitored', detail: 'No estimate of valve response yet', tone: 'inactive', basis: 'not_monitored', severity: -2 },
    { id: 'generator', label: 'Generator and bearings', value: 'Not monitored', detail: 'No instruments in the model', tone: 'inactive', basis: 'not_monitored', severity: -3 },
  )
  return rows
    .map((row, index) => ({ row, index }))
    .sort((a, b) => TONE_RANK[b.row.tone] - TONE_RANK[a.row.tone] || b.row.severity - a.row.severity || a.index - b.index)
    .map(({ row }) => row)
}

export function thermocoupleRow(summary: SupervisorSummary | null): HealthRow {
  const status = summary?.status ?? null
  const base = { id: 'exhaust_thermocouple', label: 'Exhaust thermocouple', basis: 'check' as const }
  if (!status) return { ...base, value: DASH, detail: 'Checked against the twin at steady load', tone: 'inactive', basis: 'waiting', severity: -1 }
  const residual = status.exhaust_residual_k
  const residualText = residual === null ? '' : ` (reads ${residual >= 0 ? '+' : ''}${residual.toFixed(1)} K against the twin)`
  if (status.exhaust_suspect && summary?.substitute_active) {
    return { ...base, value: 'Distrusted', detail: `Model substitute active in the temperature control${residualText}`, tone: 'warning', severity: 50 }
  }
  if (status.exhaust_suspect) {
    return { ...base, value: 'Distrusted', detail: `${status.exhaust_reason ?? 'Disagrees with the twin'}`, tone: 'alarm', severity: 100 }
  }
  if (summary?.substitute_active) {
    return { ...base, value: 'Substituted', detail: 'Model substitute still in the control; confirm the repair to return to the thermocouple', tone: 'warning', severity: 40 }
  }
  if (residual === null) return { ...base, value: 'Not yet checked', detail: 'Checked against the twin at steady load', tone: 'inactive', basis: 'waiting', severity: -1 }
  return { ...base, value: 'Trusted', detail: `Agrees with the twin${residualText}`, tone: 'normal', severity: Math.abs(residual) / 100 }
}

// ------------------------------------------------------------------ unit now

export interface UnitValue { id: string; label: string; value: string; reference: string | null; tone: Tone }

export function stateLabel(state: SimState): string {
  return STATE_LABELS[state.state] ?? state.state
}

export function tripLabel(state: SimState): string | null {
  if (state.state !== 'tripped') return null
  return state.trip_cause ? TRIP_LABELS[state.trip_cause] ?? state.trip_cause : 'Tripped'
}

/** Exhaust within this many kelvin of the control limit shows as a warning. */
export const EXHAUST_NEAR_LIMIT_K = 5

export function unitNow(state: SimState, summary: SupervisorSummary | null): UnitValue[] {
  const demand = summary?.demand_mw ?? null
  const band = summary?.band_mw ?? null
  const power = state.electrical_power_mw
  const outOfBand = band !== null && state.state === 'loaded' && (power < band[0] - 0.5 || power > band[1] + 0.5)
  const exhaustC = state.exhaust_temperature_c
  const limitC = kToC(state.temperature_limit_k)
  const margin = state.temperature_limit_k - state.exhaust_temperature_k
  const exhaustTone: Tone = margin < 0 ? 'alarm' : margin < EXHAUST_NEAR_LIMIT_K && state.flame ? 'warning' : 'normal'
  const trip = tripLabel(state)
  // The console shows the simulated truth; say so when the thermocouple reports something else.
  const readingK = state.measured?.exhaust_temperature_k
  const readingNote = readingK !== undefined && Math.abs(readingK - state.exhaust_temperature_k) > 5 ? ` · thermocouple reads ${kToC(readingK).toFixed(0)} °C` : ''
  return [
    { id: 'power', label: 'Power', value: `${power.toFixed(1)} MW`, reference: demand === null ? 'no demand set' : `demand ${demand.toFixed(1)} MW`, tone: outOfBand ? 'warning' : 'normal' },
    { id: 'exhaust', label: 'Exhaust', value: `${exhaustC.toFixed(0)} °C`, reference: `limit ${limitC.toFixed(0)} °C${readingNote}`, tone: exhaustTone },
    { id: 'heat_rate', label: 'Heat rate', value: state.heat_rate_kj_per_kwh === null ? DASH : `${state.heat_rate_kj_per_kwh.toFixed(0)} kJ/kWh`, reference: null, tone: 'normal' },
    { id: 'state', label: 'State', value: trip ? `Tripped: ${trip}` : stateLabel(state), reference: null, tone: trip ? 'alarm' : 'normal' },
    { id: 'mode', label: 'Mode', value: summary ? MODE_LABELS[summary.mode] : 'No supervisor', reference: summary?.substitute_active ? 'model exhaust substitute' : null, tone: summary?.substitute_active ? 'warning' : 'normal' },
  ]
}

// ------------------------------------------------------------------ recommendation

export interface RecommendationView {
  decision: Decision
  open: boolean
  title: string
  statusLabel: string
  tone: Tone
  gain: string | null
  approved: boolean
  failedChecks: Array<{ name: string; label: string; detail: string }>
}

/**
 * The one decision the action card shows: an escalated one first, then one waiting in
 * advisory mode, newest first; with nothing open, the latest decision the layer applied.
 */
export function currentRecommendation(summary: SupervisorSummary | null): RecommendationView | null {
  if (!summary) return null
  const open = [...summary.open_decisions].sort((a, b) => (a.status === 'escalated' ? 0 : 1) - (b.status === 'escalated' ? 0 : 1) || b.id - a.id)
  const decision = open[0] ?? [...(summary.recent_decisions ?? [])].reverse().find((d) => d.status === 'applied' || d.status === 'accepted') ?? null
  if (!decision) return null
  const isOpen = decision.status === 'pending' || decision.status === 'escalated'
  const failedChecks = decision.verdict.checks
    .filter((check) => !check.passed)
    .map((check) => ({ name: check.name, label: CHECK_LABELS[check.name] ?? check.name.replaceAll('_', ' '), detail: check.detail }))
  return {
    decision,
    open: isOpen,
    title: PROBLEM_LABELS[decision.problem] ?? decision.problem,
    statusLabel: STATUS_LABELS[decision.status] ?? decision.status,
    // Waiting for the operator is not a process alarm: escalated shows as an alert, pending stays neutral.
    tone: decision.status === 'escalated' ? 'warning' : 'normal',
    gain: expectedGain(decision),
    approved: decision.verdict.approved,
    failedChecks,
  }
}

function num(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export function expectedGain(decision: Decision): string | null {
  const o = decision.objective
  if (decision.problem === 'load_setpoint') {
    const gain = num(o.heat_rate_gain_pct)
    return gain === null ? null : `Heat rate ${gain >= 0 ? '-' : '+'}${Math.abs(gain).toFixed(2)} % against now`
  }
  if (decision.problem === 'compressor_wash') {
    const loss = num(o.loss_usd_per_h)
    const threshold = num(o.threshold_usd_per_h)
    return loss === null ? null : `Removes a fouling cost of ${loss.toFixed(2)} $/h${threshold === null ? '' : ` (wash pays above ${threshold.toFixed(2)} $/h)`}`
  }
  if (decision.problem === 'exhaust_feedback') {
    const residual = num(o.exhaust_residual_k)
    return residual === null ? 'Keeps the temperature control on a trusted value' : `Removes a ${Math.abs(residual).toFixed(1)} K error from the temperature control`
  }
  return null
}

// ------------------------------------------------------------------ mode switch

export interface ModeSwitchState {
  /** The mode the server reports. */
  current: SupervisorMode | null
  /** A mode the operator asked for that the server has not confirmed yet. */
  requested: SupervisorMode | null
  error: string | null
}

export type ModeSwitchEvent =
  | { type: 'request'; mode: SupervisorMode }
  | { type: 'confirmed'; mode: SupervisorMode }
  | { type: 'failed'; message: string }
  | { type: 'server'; mode: SupervisorMode | null }

export function modeSwitchReducer(state: ModeSwitchState, event: ModeSwitchEvent): ModeSwitchState {
  switch (event.type) {
    case 'request':
      if (state.requested !== null || event.mode === state.current) return state
      return { ...state, requested: event.mode, error: null }
    case 'confirmed':
      return { current: event.mode, requested: null, error: null }
    case 'failed':
      return { ...state, requested: null, error: event.message }
    case 'server':
      // A poll that lands while a switch is in flight does not undo the operator's choice.
      return state.requested !== null ? state : { ...state, current: event.mode }
  }
}

/** The mode the segmented control shows as selected. */
export function displayedMode(state: ModeSwitchState): SupervisorMode | null {
  return state.requested ?? state.current
}

// ------------------------------------------------------------------ stage

/** Visual rotor speed in rad/s of the model for a shaft speed in per unit (not to scale). */
export const VISUAL_RAD_PER_S_AT_RATED = 7

export function rotorRadPerSecond(speedPu: number, reduceMotion: boolean): number {
  if (reduceMotion || !Number.isFinite(speedPu)) return 0
  return Math.max(0, Math.min(1.2, speedPu)) * VISUAL_RAD_PER_S_AT_RATED
}

/**
 * Heat of the hot section from 0 (cold) to 1 (at the exhaust temperature control limit),
 * above 1 when over the limit. Below `coldK` it reads cold.
 */
export function heatFraction(exhaustK: number, limitK: number, coldK = 550): number {
  if (!Number.isFinite(exhaustK) || !Number.isFinite(limitK) || limitK <= coldK) return 0
  return Math.max(0, Math.min(1.25, (exhaustK - coldK) / (limitK - coldK)))
}

export interface Callout { id: 'compressor' | 'combustor' | 'turbine' | 'exhaust'; label: string; value: string; tone: Tone }

export function stageCallouts(state: SimState, summary: SupervisorSummary | null): Callout[] {
  const rows = rankComponents(summary)
  const row = (id: string) => rows.find((r) => r.id === id)
  const flow = row('compressor_flow')
  const turbine = row('turbine_efficiency')
  const tc = thermocoupleRow(summary)
  const margin = state.temperature_limit_k - state.exhaust_temperature_k
  const exhaustTone: Tone = tc.tone === 'alarm' || margin < 0 ? 'alarm' : tc.tone === 'warning' ? 'warning' : 'normal'
  const exhaustNote = summary?.substitute_active ? 'model substitute active' : tc.value === 'Distrusted' ? 'thermocouple distrusted' : null
  const flame = state.state === 'tripped' ? 'Flame out (trip)' : state.flame ? 'Flame on' : 'No flame'
  return [
    { id: 'compressor', label: 'Compressor flow', value: flow?.basis === 'estimate' ? flow.value.split(' ±')[0] : 'estimating', tone: flow?.tone === 'inactive' ? 'normal' : flow?.tone ?? 'normal' },
    { id: 'combustor', label: 'Combustor', value: flame, tone: state.state === 'tripped' ? 'alarm' : 'normal' },
    { id: 'turbine', label: 'Turbine efficiency', value: turbine?.basis === 'estimate' ? turbine.value.split(' ±')[0] : 'estimating', tone: turbine?.tone === 'inactive' ? 'normal' : turbine?.tone ?? 'normal' },
    { id: 'exhaust', label: 'Exhaust', value: `${state.exhaust_temperature_c.toFixed(0)} °C${exhaustNote ? ` · ${exhaustNote}` : ''}`, tone: exhaustTone },
  ]
}

// ------------------------------------------------------------------ trend

export type TrendChannel = 'power_exhaust' | 'power' | 'exhaust' | 'heat_rate' | 'speed'

export const TREND_CHANNELS: Array<{ id: TrendChannel; label: string }> = [
  { id: 'power_exhaust', label: 'Power and exhaust vs limit' },
  { id: 'power', label: 'Power vs demand' },
  { id: 'exhaust', label: 'Exhaust vs limit' },
  { id: 'heat_rate', label: 'Heat rate' },
  { id: 'speed', label: 'Shaft speed' },
]

export interface TrendLane {
  id: string
  label: string
  unit: string
  digits: number
  values: Array<{ t: number; v: number | null }>
  reference?: { label: string; values: Array<{ t: number; v: number | null }> }
}

export function trendLanes(channel: TrendChannel, samples: SimState[], demands: Array<{ t: number; mw: number | null }>): TrendLane[] {
  const demandAt = (t: number) => {
    let value: number | null = null
    for (const d of demands) {
      if (d.t <= t + 1e-6) value = d.mw
      else break
    }
    return value
  }
  const power: TrendLane = {
    id: 'power', label: 'Power', unit: 'MW', digits: 1,
    values: samples.map((s) => ({ t: s.t_s, v: s.electrical_power_mw })),
    reference: { label: 'demand', values: samples.map((s) => ({ t: s.t_s, v: demandAt(s.t_s) })) },
  }
  const exhaust: TrendLane = {
    id: 'exhaust', label: 'Exhaust', unit: '°C', digits: 0,
    values: samples.map((s) => ({ t: s.t_s, v: s.exhaust_temperature_c })),
    reference: { label: 'limit', values: samples.map((s) => ({ t: s.t_s, v: kToC(s.temperature_limit_k) })) },
  }
  if (channel === 'power_exhaust') return [power, exhaust]
  if (channel === 'power') return [power]
  if (channel === 'exhaust') return [exhaust]
  if (channel === 'heat_rate') return [{ id: 'heat_rate', label: 'Heat rate', unit: 'kJ/kWh', digits: 0, values: samples.map((s) => ({ t: s.t_s, v: s.heat_rate_kj_per_kwh })) }]
  return [{ id: 'speed', label: 'Speed', unit: '%', digits: 1, values: samples.map((s) => ({ t: s.t_s, v: s.speed_pu * 100 })) }]
}

/** Min and max over the values and the reference, padded so a flat line is not on an edge. */
export function laneRange(lane: TrendLane): [number, number] {
  const all = [...lane.values, ...(lane.reference?.values ?? [])].map((p) => p.v).filter((v): v is number => v !== null && Number.isFinite(v))
  if (all.length === 0) return [0, 1]
  let lo = Math.min(...all)
  let hi = Math.max(...all)
  const pad = Math.max((hi - lo) * 0.08, Math.abs(hi) * 0.002, 0.5)
  lo -= pad
  hi += pad
  return [lo, hi]
}
