export const MISSING_VALUE = '—'

export function signedNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return MISSING_VALUE
  if (value === 0) return (0).toFixed(digits)
  return `${value > 0 ? '+' : '−'}${Math.abs(value).toFixed(digits)}`
}

export function numberText(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return MISSING_VALUE
  return value.toFixed(digits)
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

export function zeroIsMuted(value: number): boolean {
  return value === 0
}
