import type { TwinMetric } from '../../types'
import { presentMetricValue } from '../../lib/format'
import { ValueWithUnit } from '../../lib/ValueWithUnit'

export function ReferenceMetric({ metric }: { metric: TwinMetric }) {
  if (metric.reference_value === null) return null
  const presented = presentMetricValue(metric.reference_value, metric.key, metric.unit, metric.provenance)
  return <span className="metric-provenance">Reference <ValueWithUnit value={presented.value} unit={presented.unit} /></span>
}
