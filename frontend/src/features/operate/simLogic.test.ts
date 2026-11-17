import { describe, expect, it } from 'vitest'
import { commandSummary, formatSimTime, isAllowed, mergeSamples, parseBounded, stateTone } from './simLogic'
import type { SimState } from './simTypes'

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
