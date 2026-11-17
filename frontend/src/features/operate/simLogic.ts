import type { SimState } from './simTypes'

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
