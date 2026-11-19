import { describe, expect, it } from 'vitest'
import {
  activeFaults,
  buildDegradation,
  buildSensorFault,
  commandSummary,
  formatSimTime,
  instrumentRows,
  isAllowed,
  mergeSamples,
  parseBounded,
  sensorMagnitudeUnit,
  stateTone,
} from './simLogic'
import type { SimInjectedFaults, SimState } from './simTypes'

const sample = (step: number): SimState => ({ step, t_s: step * 0.05, available_commands: ['start', 'trip'] } as unknown as SimState)

describe('parseBounded', () => {
  it('accepts values inside the range, including the bounds', () => {
    expect(parseBounded('30', 0, 47)).toBe(30)
    expect(parseBounded('0', 0, 47)).toBe(0)
    expect(parseBounded('47', 0, 47)).toBe(47)
    expect(parseBounded(' 12.5 ', 0, 47)).toBe(12.5)
  })
  it('rejects empty, non-numeric, non-finite and out-of-range input', () => {
    for (const text of ['', '  ', 'abc', 'NaN', 'Infinity', '-1', '47.01', '1e999']) {
      expect(parseBounded(text, 0, 47)).toBeNull()
    }
  })
})

describe('mergeSamples', () => {
  it('appends only samples newer than the last held step', () => {
    const merged = mergeSamples([sample(1), sample(2)], [sample(2), sample(3), sample(4)])
    expect(merged.map((s) => s.step)).toEqual([1, 2, 3, 4])
  })
  it('keeps only the most recent samples up to the cap', () => {
    const merged = mergeSamples([], Array.from({ length: 10 }, (_, i) => sample(i)), 4)
    expect(merged.map((s) => s.step)).toEqual([6, 7, 8, 9])
  })
  it('does not mutate its inputs', () => {
    const previous = [sample(1)]
    mergeSamples(previous, [sample(2)])
    expect(previous).toHaveLength(1)
  })
})

describe('helpers', () => {
  it('reads command availability from the server list only', () => {
    expect(isAllowed(sample(0), 'start')).toBe(true)
    expect(isAllowed(sample(0), 'reset')).toBe(false)
    expect(isAllowed(null, 'start')).toBe(false)
  })
  it('formats simulated time with hours only when needed', () => {
    expect(formatSimTime(0)).toBe('00:00')
    expect(formatSimTime(236.9)).toBe('03:56')
    expect(formatSimTime(3725)).toBe('1:02:05')
  })
  it('maps unit states to tones', () => {
    expect(stateTone('tripped')).toBe('negative')
    expect(stateTone('loaded')).toBe('positive')
    expect(stateTone('standstill')).toBe('neutral')
    expect(stateTone('accelerate')).toBe('warning')
  })
  it('summarises commands for the event log', () => {
    expect(commandSummary('start', {})).toBe('start')
    expect(commandSummary('set_load', { mw: 30, ramp_mw_per_min: 10 })).toBe('set load (mw 30, ramp mw per min 10)')
  })
})

describe('fault injection helpers', () => {
  it('builds degradation params and rejects out-of-range or empty faults', () => {
    expect(buildDegradation('compressor_fouling', '3', '2')).toEqual({ params: { kind: 'compressor_fouling', severity_pct: 3, rate_pct_per_h: 2 } })
    expect(buildDegradation('turbine_erosion', '1.5', '')).toEqual({ params: { kind: 'turbine_erosion', severity_pct: 1.5, rate_pct_per_h: 0 } })
    expect(buildDegradation('turbine_erosion', '6', '0')).toEqual({ error: expect.stringContaining('0 to 5') })
    expect(buildDegradation('compressor_fouling', '1', '11')).toEqual({ error: expect.stringContaining('growth rate') })
    expect(buildDegradation('compressor_fouling', '0', '0')).toEqual({ error: expect.stringContaining('above zero') })
  })
  it('builds sensor faults with the channel limit and no magnitude for a stuck sensor', () => {
    expect(buildSensorFault('exhaust_temperature', 'bias', '-20')).toEqual({ params: { channel: 'exhaust_temperature', mode: 'bias', magnitude: -20 } })
    expect(buildSensorFault('fuel_flow', 'stuck', 'ignored')).toEqual({ params: { channel: 'fuel_flow', mode: 'stuck' } })
    expect(buildSensorFault('exhaust_temperature', 'bias', '0')).toHaveProperty('error')
    expect(buildSensorFault('exhaust_temperature', 'drift', '101')).toEqual({ error: expect.stringContaining('K/h') })
    expect(buildSensorFault('speed', 'noise', '-0.01')).toHaveProperty('error')
    expect(buildSensorFault('speed', 'noise', '0.01')).toHaveProperty('params')
    expect(sensorMagnitudeUnit('fuel_flow', 'drift')).toBe('kg/s/h')
    expect(sensorMagnitudeUnit('fuel_flow', 'stuck')).toBeNull()
  })
  it('lists active faults with the clear target that removes each', () => {
    const faults: SimInjectedFaults = {
      degradation: { compressor_fouling: { severity_pct: 2.5, rate_pct_per_h: 3 } },
      health: { compressor_flow_capacity_delta: -0.025, compressor_efficiency_delta: -0.0125, turbine_efficiency_delta: 0 },
      sensors: {
        exhaust_temperature: { mode: 'bias', magnitude: -20, unit: 'K', since_s: 10 },
        fuel_flow: { mode: 'stuck', magnitude: null, unit: 'kg/s', since_s: 12, stuck_value: 2.1704 },
      },
      fuel_valve_lag_s: 2.5,
    }
    expect(activeFaults(faults).map((f) => [f.target, f.detail])).toEqual([
      ['compressor_fouling', '2.50 %, growing 3 %/h'],
      ['exhaust_temperature', 'bias -20 K'],
      ['fuel_flow', 'stuck at 2.170 kg/s'],
      ['fuel_valve', 'lag 2.5 s'],
    ])
    expect(activeFaults(undefined)).toEqual([])
  })
  it('pairs each true value with its instrument reading', () => {
    const state = {
      electrical_power_mw: 30, exhaust_temperature_k: 760, speed_pu: 1, compressor_discharge_temperature_k: 650,
      compressor_discharge_pressure_kpa: 1200, fuel_flow_kg_s: 2,
      measured: { electrical_power_mw: 30.1, exhaust_temperature_k: 740, speed_pu: 1.0001, compressor_discharge_temperature_k: 650.2, compressor_discharge_pressure_kpa: 1201, fuel_flow_kg_s: 2.01 },
    } as unknown as SimState
    const rows = instrumentRows(state)
    expect(rows.map((r) => r.channel)).toEqual(['electrical_power', 'exhaust_temperature', 'speed', 'compressor_discharge_temperature', 'compressor_discharge_pressure', 'fuel_flow'])
    expect(rows[1]).toMatchObject({ truth: 760, measured: 740, unit: 'K' })
  })
})
