import type { TwinMetric } from '../../types'
import { presentMetricValue } from '../../lib/format'
import type { PresentedMetricValue } from '../../lib/format'

export function presentMetric(metric: TwinMetric): PresentedMetricValue {
  return presentMetricValue(metric.value, metric.key, metric.unit, metric.provenance)
}

export function statusLabel(label: string): string {
  const normalized = label.trim().toLowerCase()
  if (normalized.includes('drift')) return 'Drift'
  if (normalized.includes('modelled')) return 'Modelled'
  if (normalized.includes('comparison')) return 'Comparison'
  return label
}
