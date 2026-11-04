export const MISSING_VALUE = '—'

export function fixedNumber(value: number, digits: number): string {
  const adjustment = Math.sign(value) * Number.EPSILON * Math.max(1, Math.abs(value))
  return (value + adjustment).toFixed(digits)
}

export function signedNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return MISSING_VALUE
  if (value === 0) return (0).toFixed(digits)
  return `${value > 0 ? '+' : '−'}${fixedNumber(Math.abs(value), digits)}`
}

export function numberText(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return MISSING_VALUE
  return fixedNumber(value, digits)
}

export function formatUtcTime(value: string | null | undefined): string {
  if (!value) return MISSING_VALUE
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return MISSING_VALUE
  return date.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' })
}

export function powerMw(kw: number | null | undefined, digits = 2): string {
  return numberText(kw === null || kw === undefined ? null : kw / 1000, digits)
}

export function celsiusToKelvin(value: number): number {
  return value + 273.15
}

export interface PresentedMetricValue {
  value: string
  unit?: string
  provenance: string
}

export function presentMetricValue(value: number | boolean, key: string, unit: string, provenance: string): PresentedMetricValue {
  if (typeof value === 'boolean') return { value: value ? 'Yes' : 'No', provenance }
  if (key.includes('efficiency')) return { value: fixedNumber(value * 100, 1), unit: '%', provenance }
  if (unit === '°C' || unit === 'C') {
    return { value: fixedNumber(celsiusToKelvin(value), 1), unit: 'K', provenance: `${provenance} · Original source value ${fixedNumber(value, 1)} °C.` }
  }
  if (unit === 'K') return { value: fixedNumber(value, 1), unit, provenance }
  if (unit === 'MW' || unit === 'kW') return { value: numberText(value, 2), unit, provenance }
  return { value: numberText(value, 2), unit: unit || undefined, provenance }
}

export function metricNumber(value: number | boolean, key: string, unit: string): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  if (key.includes('efficiency')) return value * 100
  if (unit === '°C' || unit === 'C') return celsiusToKelvin(value)
  return value
}

export function zeroIsMuted(value: number): boolean {
  return value === 0
}
