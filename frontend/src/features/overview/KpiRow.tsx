import { ArrowDown, ArrowUp, Minus } from 'lucide-react'
import { useTurbineStore } from '../../app/useTurbineStore'
import type { TimelinePoint, TwinSnapshot } from '../../types'
import { powerMw, signedNumber } from '../../lib/format'
import { ValueWithUnit } from '../../lib/ValueWithUnit'
import './KpiRow.css'

export function KpiRow({ snapshot, timeline }: { snapshot: TwinSnapshot; timeline: TimelinePoint[] }) {
  const { state } = useTurbineStore()
  const flagged = timeline.filter((row) => row.anomaly_flag).length
  const residual = snapshot.power_residual_kw / 1000
  const Marker = residual > 0 ? ArrowUp : residual < 0 ? ArrowDown : Minus
  return (
    <section className="kpi-row" aria-label="Selected sample summary">
      <div className="kpi-item"><div className="kpi-label">Reference model</div><div className="kpi-value"><ValueWithUnit value={powerMw(snapshot.model_electrical_power_kw)} unit="MW" /></div><div className="kpi-detail">Simplified model output</div></div>
      <div className="kpi-item"><div className="kpi-label">Synthetic observation</div><div className="kpi-value"><ValueWithUnit value={powerMw(snapshot.synthetic_observed_power_kw)} unit="MW" /></div><div className="kpi-detail">Selected synthetic sample</div></div>
      <div className={`kpi-item kpi-residual ${residual > 0 ? 'is-positive' : residual < 0 ? 'is-negative' : 'is-zero'}`}>
        <div className="kpi-label">Residual</div>
        <div className="kpi-value"><Marker size={16} strokeWidth={1.7} aria-hidden="true" /><ValueWithUnit value={signedNumber(residual)} unit="MW" /></div>
        <div className="kpi-detail">Observation − reference model</div>
      </div>
      <div className="kpi-item"><div className="kpi-label">Flagged samples</div><div className="kpi-value"><ValueWithUnit value={`${flagged} / ${state.run?.run.sample_count ?? timeline.length}`} /></div><div className="kpi-detail">Residual screen</div></div>
    </section>
  )
}
