import { describe, expect, it } from 'vitest'
import type { SimState } from '../operate/simTypes'
import type { Decision, SupervisorSummary, TwinStatus } from './supervisorTypes'
import {
  currentRecommendation,
  displayedMode,
  expectedGain,
  formatClock,
  formatDelta,
  heatFraction,
  laneRange,
  modeSwitchReducer,
  rankComponents,
  rotorRadPerSecond,
  stageCallouts,
  trendLanes,
  unitNow,
} from './twinLogic'

function status(overrides: Partial<TwinStatus> = {}): TwinStatus {
  return {
    t_s: 600,
    loaded: true,
    steady: true,
    health: { compressor_flow: 0.002, compressor_efficiency: 0.001, turbine_efficiency: 0.004 },
    health_std: { compressor_flow: 0.0004, compressor_efficiency: 0.0002, turbine_efficiency: 0.0003 },
    estimator_updates: 12,
    mismatch_index: 0.5,
    residual_mean: {},
    exhaust_residual_k: 1.2,
    exhaust_scatter_k: 0.4,
    exhaust_suspect: false,
    exhaust_reason: null,
    model_exhaust_k: 815,
    fouling_rate_per_h: null,
    ...overrides,
  }
}

function summary(overrides: Partial<SupervisorSummary> = {}): SupervisorSummary {
  return {
    mode: 'advisory',
    demand_mw: 35,
    band_mw: [33, 37],
    substitute_active: false,
    procedure: [],
    status: status(),
    open_decisions: [],
    last_load_evaluation: null,
    last_wash_evaluation: null,
    counters: {},
    decisions_total: 0,
    recent_decisions: [],
    ...overrides,
  }
}

function decision(overrides: Partial<Decision> = {}): Decision {
  return {
    id: 1,
    t_s: 500,
    problem: 'load_setpoint',
    mode: 'advisory',
    summary: 'Run at 35.0 MW with IGV 40% open.',
    actions: [],
    objective: { heat_rate_gain_pct: 2.76 },
    verdict: { approved: true, reason: 'all guard checks passed', checks: [{ name: 'no_trip', passed: true, value: null, limit: null, detail: '' }], forward: null },
    status: 'pending',
    reason: '',
    resolved_t_s: null,
    resolved_by: null,
    ...overrides,
  }
}

function sim(overrides: Partial<SimState> = {}): SimState {
  return {
    t_s: 600, step: 6000, state: 'loaded', breaker_closed: true, flame: true, trip_cause: null, grid: 'infinite_bus',
    speed_pu: 1, speed_hz_equivalent: 50, grid_frequency_hz: 50, fsr: 0.6, limiter: 'governor', fuel_flow_kg_s: 2.4,
    electrical_power_mw: 35.02, shaft_power_mw: 35.5, load_setpoint_mw: 35, load_reference_mw: 35, ramp_mw_per_min: 10,
    exhaust_temperature_k: 813.7, exhaust_temperature_c: 540.55, temperature_limit_k: 844.15, trip_temperature_k: 884,
    igv_position: 0.8, igv_mode: 'auto', ambient_temperature_c: 15, heat_rate_kj_per_kwh: 10871,
    compressor_discharge_temperature_k: 650, compressor_discharge_pressure_kpa: 1200,
    measured: { electrical_power_mw: 35, exhaust_temperature_k: 813, speed_pu: 1, compressor_discharge_temperature_k: 650, compressor_discharge_pressure_kpa: 1200, fuel_flow_kg_s: 2.4 },
    injected_faults: { degradation: {}, health: { compressor_flow_capacity_delta: 0, compressor_efficiency_delta: 0, turbine_efficiency_delta: 0 }, sensors: {}, fuel_valve_lag_s: null },
    alarms: [], available_commands: [], synthetic_simulation: true,
    ...overrides,
  }
}

describe('formatting', () => {
  it('formats a signed health delta in percent with its uncertainty', () => {
    expect(formatDelta(-0.012, 0.0005)).toBe('-1.20 % ± 0.05')
    expect(formatDelta(0.004, null)).toBe('+0.40 %')
    expect(formatDelta(0, 0.0001)).toBe('0.00 % ± 0.01')
  })

  it('formats simulated time as a clock', () => {
    expect(formatClock(65)).toBe('01:05')
    expect(formatClock(3725.4)).toBe('1:02:05')
    expect(formatClock(-3)).toBe('00:00')
  })
})

describe('component ranking', () => {
  it('waits for an estimate instead of showing a value before the estimator has run', () => {
    const rows = rankComponents(summary({ status: status({ estimator_updates: 0, exhaust_residual_k: null }) }))
    const flow = rows.find((row) => row.id === 'compressor_flow')!
    expect(flow.value).toBe('—')
    expect(flow.basis).toBe('waiting')
  })

  it('puts the worst estimate first and unmonitored parts last, without inventing a score', () => {
    const rows = rankComponents(summary({
      status: status({ health: { compressor_flow: -0.031, compressor_efficiency: -0.012, turbine_efficiency: 0.001 } }),
    }))
    expect(rows.map((row) => row.id)).toEqual([
      'compressor_flow', 'compressor_efficiency', 'exhaust_thermocouple', 'turbine_efficiency', 'fuel_valve', 'generator',
    ])
    expect(rows[0]).toMatchObject({ tone: 'alarm', value: '-3.10 % ± 0.04' })
    expect(rows[1].tone).toBe('warning')
    expect(rows.find((row) => row.id === 'fuel_valve')).toMatchObject({ value: 'Not monitored', basis: 'not_monitored' })
    expect(rows.find((row) => row.id === 'generator')).toMatchObject({ value: 'Not monitored', basis: 'not_monitored' })
  })

  it('raises a distrusted thermocouple to the top, and to a warning once the substitute runs', () => {
    const suspect = status({ exhaust_suspect: true, exhaust_reason: 'reads -68.8 K against the twin', exhaust_residual_k: -68.8 })
    expect(rankComponents(summary({ status: suspect }))[0]).toMatchObject({ id: 'exhaust_thermocouple', tone: 'alarm', value: 'Distrusted' })
    const substituted = rankComponents(summary({ status: suspect, substitute_active: true }))[0]
    expect(substituted).toMatchObject({ id: 'exhaust_thermocouple', tone: 'warning' })
    expect(substituted.detail).toContain('Model substitute active')
  })
})

describe('recommendation', () => {
  it('shows an escalated decision before a pending one, with its failed checks', () => {
    const failed = { approved: false, reason: 'x', checks: [{ name: 'model_mismatch', passed: false, value: 3, limit: 2, detail: 'no steady residuals yet' }], forward: null }
    const view = currentRecommendation(summary({
      open_decisions: [decision({ id: 3 }), decision({ id: 2, status: 'escalated', verdict: failed })],
    }))!
    expect(view.decision.id).toBe(2)
    expect(view).toMatchObject({ open: true, tone: 'warning', approved: false, statusLabel: 'Escalated to you' })
    expect(view.failedChecks).toEqual([{ name: 'model_mismatch', label: 'Twin agrees with the plant', detail: 'no steady residuals yet' }])
  })

  it('falls back to the latest applied decision when nothing is open', () => {
    const view = currentRecommendation(summary({ recent_decisions: [decision({ id: 1, status: 'superseded' }), decision({ id: 2, status: 'applied' })] }))!
    expect(view.decision.id).toBe(2)
    expect(view.open).toBe(false)
    expect(currentRecommendation(summary())).toBeNull()
    expect(currentRecommendation(null)).toBeNull()
  })

  it('states the expected gain per problem', () => {
    expect(expectedGain(decision())).toBe('Heat rate -2.76 % against now')
    expect(expectedGain(decision({ problem: 'compressor_wash', objective: { loss_usd_per_h: 3.2, threshold_usd_per_h: 1.1 } }))).toBe('Removes a fouling cost of 3.20 $/h (wash pays above 1.10 $/h)')
    expect(expectedGain(decision({ problem: 'exhaust_feedback', objective: { exhaust_residual_k: -68.8 } }))).toBe('Removes a 68.8 K error from the temperature control')
  })
})

describe('mode switch', () => {
  it('shows the requested mode until the server confirms it', () => {
    let state = modeSwitchReducer({ current: 'advisory', requested: null, error: null }, { type: 'request', mode: 'autonomous' })
    expect(displayedMode(state)).toBe('autonomous')
    state = modeSwitchReducer(state, { type: 'server', mode: 'advisory' })
    expect(displayedMode(state)).toBe('autonomous')
    state = modeSwitchReducer(state, { type: 'request', mode: 'manual' })
    expect(state.requested).toBe('autonomous')
    state = modeSwitchReducer(state, { type: 'confirmed', mode: 'autonomous' })
    expect(state).toEqual({ current: 'autonomous', requested: null, error: null })
  })

  it('falls back to the server mode with an error when the switch fails, and ignores a no-op', () => {
    const start = { current: 'manual' as const, requested: null, error: null }
    expect(modeSwitchReducer(start, { type: 'request', mode: 'manual' })).toBe(start)
    const failed = modeSwitchReducer(modeSwitchReducer(start, { type: 'request', mode: 'advisory' }), { type: 'failed', message: 'offline' })
    expect(displayedMode(failed)).toBe('manual')
    expect(failed.error).toBe('offline')
  })
})

describe('unit now and stage', () => {
  it('lists five values with the exhaust against its limit and flags a trip', () => {
    const values = unitNow(sim(), summary())
    expect(values.map((v) => v.id)).toEqual(['power', 'exhaust', 'heat_rate', 'state', 'mode'])
    expect(values[0]).toMatchObject({ value: '35.0 MW', reference: 'demand 35.0 MW', tone: 'normal' })
    expect(values[1]).toMatchObject({ value: '541 °C', reference: 'limit 571 °C', tone: 'normal' })
    const tripped = unitNow(sim({ state: 'tripped', trip_cause: 'exhaust_over_temperature', flame: false }), summary())
    expect(tripped[3]).toMatchObject({ value: 'Tripped: Exhaust over-temperature', tone: 'alarm' })
    expect(unitNow(sim({ exhaust_temperature_k: 850 }), summary())[1].tone).toBe('alarm')
    const stuck = sim({ measured: { ...sim().measured, exhaust_temperature_k: 746.15 } })
    expect(unitNow(stuck, summary())[1].reference).toBe('limit 571 °C · thermocouple reads 473 °C')
  })

  it('maps shaft speed and exhaust temperature to rotor motion and heat', () => {
    expect(rotorRadPerSecond(1, false)).toBeGreaterThan(rotorRadPerSecond(0.3, false))
    expect(rotorRadPerSecond(1, true)).toBe(0)
    expect(rotorRadPerSecond(0, false)).toBe(0)
    expect(heatFraction(288, 844)).toBe(0)
    expect(heatFraction(844, 844)).toBeCloseTo(1)
    expect(heatFraction(870, 844)).toBeGreaterThan(1)
  })

  it('pins the substitute state on the exhaust callout', () => {
    const callouts = stageCallouts(sim(), summary({ substitute_active: true, status: status({ exhaust_suspect: true }) }))
    expect(callouts.find((c) => c.id === 'exhaust')).toMatchObject({ tone: 'warning', value: '541 °C · model substitute active' })
    expect(stageCallouts(sim({ state: 'tripped', flame: false }), null).find((c) => c.id === 'combustor')).toMatchObject({ value: 'Flame out (trip)', tone: 'alarm' })
  })
})

describe('trend', () => {
  it('builds power and exhaust lanes with demand and limit references', () => {
    const samples = [sim({ t_s: 0, electrical_power_mw: 0 }), sim({ t_s: 10, electrical_power_mw: 20 }), sim({ t_s: 20 })]
    const lanes = trendLanes('power_exhaust', samples, [{ t: 0, mw: null }, { t: 10, mw: 35 }])
    expect(lanes.map((lane) => lane.id)).toEqual(['power', 'exhaust'])
    expect(lanes[0].reference!.values.map((p) => p.v)).toEqual([null, 35, 35])
    expect(lanes[1].reference!.values[0].v).toBeCloseTo(571)
    const [lo, hi] = laneRange(lanes[0])
    expect(lo).toBeLessThan(0)
    expect(hi).toBeGreaterThan(35)
    expect(trendLanes('speed', samples, [])[0].values[0].v).toBe(100)
  })
})
