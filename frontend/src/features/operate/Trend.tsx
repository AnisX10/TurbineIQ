import type { SimState } from './simTypes'

interface TrendProps {
  title: string
  unit: string
  samples: SimState[]
  pick: (sample: SimState) => number
  digits?: number
  refLine?: { value: number; label: string }
}

const WIDTH = 320
const HEIGHT = 96
const PAD = { left: 6, right: 6, top: 8, bottom: 8 }

export function Trend({ title, unit, samples, pick, digits = 1, refLine }: TrendProps) {
  const values = samples.map(pick)
  const last = values.length ? values[values.length - 1] : null
  const lows = refLine ? [...values, refLine.value] : values
  const min = lows.length ? Math.min(...lows) : 0
  const max = lows.length ? Math.max(...lows) : 1
  const span = max - min || 1
  const t0 = samples.length ? samples[0].t_s : 0
  const t1 = samples.length ? samples[samples.length - 1].t_s : 1
  const tSpan = t1 - t0 || 1
  const x = (t: number) => PAD.left + ((t - t0) / tSpan) * (WIDTH - PAD.left - PAD.right)
  const y = (v: number) => PAD.top + (1 - (v - min) / span) * (HEIGHT - PAD.top - PAD.bottom)
  const points = samples.map((s) => `${x(s.t_s).toFixed(1)},${y(pick(s)).toFixed(1)}`).join(' ')
  const description = last === null
    ? `${title}: no data yet`
    : `${title}, latest ${last.toFixed(digits)} ${unit}, range ${min.toFixed(digits)} to ${max.toFixed(digits)} ${unit} over ${Math.round(tSpan)} seconds`

  return (
    <figure className="operate-trend">
      <figcaption>
        <span>{title}</span>
        <strong>{last === null ? '—' : `${last.toFixed(digits)} ${unit}`}</strong>
      </figcaption>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={description} preserveAspectRatio="none">
        {refLine && <line className="operate-trend-ref" x1={PAD.left} x2={WIDTH - PAD.right} y1={y(refLine.value)} y2={y(refLine.value)} />}
        {points && <polyline className="operate-trend-line" points={points} fill="none" />}
      </svg>
      <div className="operate-trend-axis" aria-hidden="true">
        <span>{min.toFixed(digits)}</span>
        {refLine && <span>{refLine.label} {refLine.value.toFixed(digits)}</span>}
        <span>{max.toFixed(digits)}</span>
      </div>
    </figure>
  )
}
