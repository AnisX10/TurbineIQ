import { celsiusToKelvin, fixedNumber } from '../../lib/format'
import { PUBLISHED_6B03_REFERENCE } from '../../lib/publishedReference'
import { ValueWithUnit } from '../../lib/ValueWithUnit'

export function PublishedReferenceBlock() {
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
      <small>Source: {PUBLISHED_6B03_REFERENCE.source}{originalTemperature ? `. Original exhaust temperature: ${originalTemperature.value} ${originalTemperature.unit}.` : ''}</small>
    </section>
  )
}
