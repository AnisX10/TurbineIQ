import type { TwinComponentState } from '../../types'
import { ValueWithUnit } from '../../lib/ValueWithUnit'
import { presentMetric } from './metricFormatting'
import { ReferenceMetric } from './metricPresentation'
import './ComponentMetrics.css'

export function ComponentMetrics({ component }: { component: TwinComponentState }) {
  return (
    <div className="selected-component-metrics">
      <h3>{component.label} metrics</h3>
      {component.metrics.slice(0, 4).map((metric) => {
        const presented = presentMetric(metric)
        return <div className="selected-metric" key={metric.key}><span>{metric.label}</span><ValueWithUnit value={presented.value} unit={presented.unit} /><span className="metric-provenance">{presented.provenance}</span><ReferenceMetric metric={metric} /></div>
      })}
    </div>
  )
}
