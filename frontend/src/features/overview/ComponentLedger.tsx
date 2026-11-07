import type { ComponentId } from '../../app/router'
import type { TwinSnapshot } from '../../types'
import { ValueWithUnit } from '../../lib/ValueWithUnit'
import { PublishedReferenceBlock } from './PublishedReference'
import { presentMetric, statusLabel } from './metricFormatting'
import { ComponentMetrics } from './ComponentMetrics'
import { setPartPickerHost } from './partPickerHost'
import './ComponentLedger.css'

export function ComponentLedger({ snapshot, selectedId, onSelect }: { snapshot: TwinSnapshot; selectedId: ComponentId; onSelect: (id: ComponentId) => void }) {
  const selected = snapshot.components.find((component) => component.component_id === selectedId) ?? snapshot.components[0]
  const knownIds = new Set(['inlet', 'compressor', 'combustor', 'turbine', 'shaft', 'generator'])
  return (
    <section className="component-ledger panel" aria-labelledby="component-ledger-title">
      <div className="card-heading"><h2 id="component-ledger-title">Component ledger</h2><span>{snapshot.components.length} components</span></div>
      <div className="component-rows">
        {snapshot.components.map((component) => {
          const metric = component.metrics[0]
          const id = knownIds.has(component.component_id) ? component.component_id as ComponentId : 'compressor'
          const primary = metric ? presentMetric(metric) : null
          return <button type="button" key={component.component_id} className={`component-row ${id === selectedId ? 'is-selected' : ''}`} aria-pressed={id === selectedId} onClick={() => onSelect(id)}><span className="component-name">{component.label}</span><span className="neutral-status">{statusLabel(component.status_label)}</span><span className="component-primary" title={metric ? `${metric.label}: ${primary?.value} ${primary?.unit ?? ''}` : undefined}>{primary ? <ValueWithUnit value={primary.value} unit={primary.unit} /> : '—'}</span></button>
        })}
      </div>
      {selected && <ComponentMetrics component={selected} />}
      <div className="mesh-picker-slot" id="component-part-picker-slot" ref={setPartPickerHost} />
      <PublishedReferenceBlock />
      {selected && <a className="component-detail-link" href={`#/components/${selected.component_id}?scenario=${encodeURIComponent(snapshot.scenario_id)}&seed=${snapshot.seed}&i=${snapshot.sample_index}`}>Open component detail</a>}
    </section>
  )
}
