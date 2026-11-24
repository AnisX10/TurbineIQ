import { useId, useState } from 'react'
import type { SimState } from '../operate/simTypes'
import type { TrendChannel, TrendLane } from './twinLogic'
import { TREND_CHANNELS, formatClock, laneRange, trendLanes } from './twinLogic'

const WIDTH = 600
const LANE_HEIGHT = 120

function path(points: Array<{ t: number; v: number | null }>, x: (t: number) => number, y: (v: number) => number): string {
  let d = ''
  let pen = false
  for (const p of points) {
    if (p.v === null || !Number.isFinite(p.v)) {
      pen = false
      continue
    }
    d += `${pen ? 'L' : 'M'}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`
    pen = true
  }
  return d
}

function Lane({ lane, t0, t1, height }: { lane: TrendLane; t0: number; t1: number; height: number }) {
  const [lo, hi] = laneRange(lane)
  const x = (t: number) => ((t - t0) / (t1 - t0 || 1)) * WIDTH
  const y = (v: number) => 6 + (1 - (v - lo) / (hi - lo || 1)) * (height - 12)
  const last = [...lane.values].reverse().find((p) => p.v !== null)?.v ?? null
  const ref = lane.reference ? [...lane.reference.values].reverse().find((p) => p.v !== null)?.v ?? null : null
  const description = last === null
    ? `${lane.label}: no data yet`
    : `${lane.label} ${last.toFixed(lane.digits)} ${lane.unit}${ref !== null && lane.reference ? `, ${lane.reference.label} ${ref.toFixed(lane.digits)} ${lane.unit}` : ''}, range ${lo.toFixed(lane.digits)} to ${hi.toFixed(lane.digits)} ${lane.unit}`
  return (
    <div className="twin-lane">
      <div className="twin-lane-head">
        <span>{lane.label}</span>
        <strong>{last === null ? '—' : last.toFixed(lane.digits)}<span className="unit">{lane.unit}</span></strong>
        {lane.reference && ref !== null && <span className="twin-lane-ref"><span className="twin-ref-swatch" aria-hidden="true" />{lane.reference.label} {ref.toFixed(lane.digits)}</span>}
      </div>
      <div className="twin-lane-plot">
        <svg viewBox={`0 0 ${WIDTH} ${height}`} preserveAspectRatio="none" role="img" aria-label={description}>
          {[0.25, 0.5, 0.75].map((f) => <line key={f} className="twin-grid-line" x1={0} x2={WIDTH} y1={height * f} y2={height * f} />)}
          {lane.reference && <path className="twin-trend-ref" d={path(lane.reference.values, x, y)} />}
          <path className="twin-trend-line" d={path(lane.values, x, y)} />
        </svg>
        <span className="twin-lane-axis twin-lane-axis--hi" aria-hidden="true">{hi.toFixed(lane.digits)}</span>
        <span className="twin-lane-axis twin-lane-axis--lo" aria-hidden="true">{lo.toFixed(lane.digits)}</span>
      </div>
    </div>
  )
}

export function TwinTrend({ samples, demands }: { samples: SimState[]; demands: Array<{ t: number; mw: number | null }> }) {
  const [channel, setChannel] = useState<TrendChannel>('power_exhaust')
  const selectId = useId()
  const lanes = trendLanes(channel, samples, demands)
  const t0 = samples[0]?.t_s ?? 0
  const t1 = samples[samples.length - 1]?.t_s ?? 1
  const height = lanes.length > 1 ? LANE_HEIGHT * 0.8 : LANE_HEIGHT * 1.5
  return (
    <section className="twin-card twin-trend" aria-labelledby="twin-trend-title">
      <div className="twin-card-head">
        <h2 id="twin-trend-title">Trend</h2>
        <label className="twin-select" htmlFor={selectId}>
          <span className="twin-sr">Trend channel</span>
          <select id={selectId} value={channel} onChange={(event) => setChannel(event.target.value as TrendChannel)}>
            {TREND_CHANNELS.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
          </select>
        </label>
      </div>
      <div className="twin-lanes">
        {lanes.map((lane) => <Lane key={lane.id} lane={lane} t0={t0} t1={t1} height={height} />)}
      </div>
      <div className="twin-time-axis" aria-hidden="true"><span>{formatClock(t0)}</span><span>simulated time</span><span>{formatClock(t1)}</span></div>
    </section>
  )
}
