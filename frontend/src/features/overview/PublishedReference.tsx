import { useTurbineStore } from '../../app/useTurbineStore'
import { celsiusToKelvin, fixedNumber } from '../../lib/format'
import { PUBLISHED_6B03_REFERENCE } from '../../lib/publishedReference'
import { ValueWithUnit } from '../../lib/ValueWithUnit'
import type { PublishedReferenceRow } from '../../types'

function signedPercent(value: number) {
  const rounded = Math.round(value)
  return `${rounded > 0 ? '+' : rounded < 0 ? '−' : ''}${Math.abs(rounded)}%`
}

function modelValue(row: PublishedReferenceRow) {
  if (row.unit === '°C') return { value: fixedNumber(celsiusToKelvin(row.model), 1), unit: 'K' }
  return { value: fixedNumber(row.model, 1), unit: row.unit === ':1' ? '' : row.unit }
}

export function PublishedReferenceBlock() {
  const { state } = useTurbineStore()
  const comparison = state.run?.run.published_reference
  const originalTemperature = PUBLISHED_6B03_REFERENCE.values.find((item) => item.label === 'Exhaust temperature')
  return (
    <section className="published-reference" aria-labelledby="published-reference-title">
      <h3 id="published-reference-title">Published 6B.03 reference</h3>
      <dl>{PUBLISHED_6B03_REFERENCE.values.map(({ label, value, unit }) => {
        const numeric = Number(value)
        const temperature = unit === '°C' && Number.isFinite(numeric)
        return <div key={label}><dt>{label}</dt><dd>{temperature ? <ValueWithUnit value={fixedNumber(celsiusToKelvin(numeric), 1)} unit="K" /> : <ValueWithUnit value={value} unit={unit} />}</dd></div>
      })}</dl>
      <p>{PUBLISHED_6B03_REFERENCE.caveat}</p>
      {comparison && (
        <details className="published-comparison">
          <summary>{comparison.calibrated ? 'Fitted model at ISO ambient, agrees by construction' : 'Model at its reference point, not calibrated'}</summary>
          <dl>{comparison.rows.map((row) => {
            const model = modelValue(row)
            return <div key={row.key}><dt>{row.label}</dt><dd><ValueWithUnit value={model.value} unit={model.unit} /> <span className="published-delta">{signedPercent(row.difference_percent)}</span></dd></div>
          })}</dl>
          <p>{comparison.model_point}. Percentages are model versus published.{comparison.calibrated ? ` ${comparison.statement}` : ''}</p>
        </details>
      )}
      <small>Source: {PUBLISHED_6B03_REFERENCE.source}{originalTemperature ? `. Original exhaust temperature: ${originalTemperature.value} ${originalTemperature.unit}.` : ''}</small>
    </section>
  )
}
