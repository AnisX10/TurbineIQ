import { describe, expect, it } from 'vitest'
import { formatUtcTime, formatUtcTimestamp, metricDigits, MISSING_VALUE, numberText, powerMw, presentMetricValue, signedNumber, zeroIsMuted } from './format'

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
    expect(formatUtcTimestamp('2026-11-04T12:00:00Z')).toBe('12:00 UTC')
    expect(formatUtcTimestamp('not a timestamp')).toBe(MISSING_VALUE)
  })

  it('presents efficiency as a percentage and temperature as kelvin with source provenance', () => {
    expect(presentMetricValue(0.812, 'compressor_efficiency', 'fraction', 'Synthetic parameter').value).toBe('81.2')
    expect(presentMetricValue(0.812, 'compressor_efficiency', 'fraction', 'Synthetic parameter').unit).toBe('%')
    expect(presentMetricValue(15, 'ambient_temperature_c', '°C', 'Synthetic input')).toEqual({
      value: '288.2',
      unit: 'K',
      provenance: 'Synthetic input · Original source value 15.0 °C.',
    })
  })

  it('keeps kelvin at one decimal and power at two decimals', () => {
    expect(presentMetricValue(288.15, 'temperature', 'K', 'Synthetic input').value).toBe('288.2')
    expect(presentMetricValue(25066.453, 'shaft_power_kw', 'kW', 'Synthetic estimate').value).toBe('25066.45')
    expect(numberText(null)).toBe('—')
    expect(metricDigits('%')).toBe(1)
    expect(metricDigits('K')).toBe(1)
    expect(metricDigits('MW')).toBe(2)
  })
})
