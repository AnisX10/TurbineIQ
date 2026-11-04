import { describe, expect, it } from 'vitest'
import { formatUtcTime, MISSING_VALUE, numberText, powerMw, signedNumber, zeroIsMuted } from './format'

describe('engineering formatters', () => {
  it('shows explicit signs and the true minus for residuals', () => {
    expect(signedNumber(1.234)).toBe('+1.23')
    expect(signedNumber(-1.234)).toBe('−1.23')
    expect(signedNumber(0)).toBe('0.00')
  })

  it('renders missing and non-finite values as an em dash', () => {
    expect(numberText(null)).toBe(MISSING_VALUE)
    expect(numberText(Number.NaN)).toBe(MISSING_VALUE)
    expect(signedNumber(Number.POSITIVE_INFINITY)).toBe(MISSING_VALUE)
  })

  it('converts kilowatts to megawatts and marks zero as muted', () => {
    expect(powerMw(26301.98)).toBe('26.30')
    expect(zeroIsMuted(0)).toBe(true)
    expect(zeroIsMuted(1)).toBe(false)
  })

  it('formats UTC time and missing timestamps', () => {
    expect(formatUtcTime('2026-11-04T18:00:00Z')).toBe('18:00')
    expect(formatUtcTime(null)).toBe(MISSING_VALUE)
  })
})
