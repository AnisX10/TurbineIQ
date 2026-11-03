import { useMemo } from 'react'
import type { TimelinePoint } from './types'

interface PowerChartProps {
  timeline: TimelinePoint[]
  selectedIndex: number
}

const WIDTH = 960
const HEIGHT = 210
const MARGIN = { top: 16, right: 16, bottom: 28, left: 58 }

function formatPower(value: number): string {
  return `${value.toFixed(1)} MW`
}

function formatTime(value: string): string {
  const date = new Date(value)
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' })
}

export function PowerChart({ timeline, selectedIndex }: PowerChartProps) {
  const chart = useMemo(() => {
    const keys = [
      'model_electrical_power_kw',
      'synthetic_truth_electrical_power_kw',
      'observed_electrical_power_kw',
    ] as const
    const values = timeline.flatMap((row) => keys.map((key) => row[key] / 1000))
    const minValue = Math.min(...values)
    const maxValue = Math.max(...values)
    const span = Math.max(maxValue - minValue, 0.1)
    const min = Math.floor((minValue - span * 0.12) * 2) / 2
    const max = Math.ceil((maxValue + span * 0.12) * 2) / 2
    const plotWidth = WIDTH - MARGIN.left - MARGIN.right
    const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom
    const x = (index: number) => MARGIN.left + (index / Math.max(timeline.length - 1, 1)) * plotWidth
    const y = (value: number) => MARGIN.top + ((max - value) / (max - min)) * plotHeight
    const series = keys.map((key) => ({
      key,
      points: timeline
        .map((row, index) => `${x(index).toFixed(2)},${y(row[key] / 1000).toFixed(2)}`)
        .join(' '),
    }))
    const tickValues = Array.from({ length: 4 }, (_, index) => max - ((max - min) * index) / 3)
    return { x, y, series, tickValues, min, max }
  }, [timeline])

  const selected = timeline[selectedIndex]
  const selectedX = chart.x(selectedIndex)
  const observedY = selected ? chart.y(selected.observed_electrical_power_kw / 1000) : 0

  return (
    <div className="power-chart">
      <div className="chart-legend" aria-label="Chart series">
        <span><i className="legend-swatch legend-reference" />Reference model</span>
        <span><i className="legend-swatch legend-truth" />Synthetic plant truth</span>
        <span><i className="legend-swatch legend-observed" />Synthetic observation</span>
      </div>
      <svg
        className="chart-svg"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label="Electrical output in megawatts over the synthetic scenario timeline"
        preserveAspectRatio="none"
      >
        {chart.tickValues.map((value, index) => {
          const y = MARGIN.top + ((HEIGHT - MARGIN.top - MARGIN.bottom) * index) / 3
          return (
            <g key={value}>
              <line x1={MARGIN.left} x2={WIDTH - MARGIN.right} y1={y} y2={y} className="chart-grid" />
              <text x={MARGIN.left - 10} y={y + 4} textAnchor="end" className="chart-axis-label">
                {value.toFixed(1)}
              </text>
            </g>
          )
        })}
        <text x={MARGIN.left} y={HEIGHT - 4} className="chart-axis-label">
          {timeline[0] ? formatTime(timeline[0].timestamp_utc) : '00:00'}
        </text>
        <text x={WIDTH / 2} y={HEIGHT - 4} textAnchor="middle" className="chart-axis-label">
          Scenario time · UTC
        </text>
        <text x={WIDTH - MARGIN.right} y={HEIGHT - 4} textAnchor="end" className="chart-axis-label">
          {timeline.at(-1) ? formatTime(timeline.at(-1)!.timestamp_utc) : '24:00'}
        </text>
        {chart.series.map((series) => (
          <polyline
            key={series.key}
            points={series.points}
            fill="none"
            className={`chart-line chart-line-${series.key}`}
            vectorEffect="non-scaling-stroke"
          >
            <title>{series.key.replaceAll('_', ' ')}</title>
          </polyline>
        ))}
        {selected && (
          <g>
            <line
              x1={selectedX}
              x2={selectedX}
              y1={MARGIN.top}
              y2={HEIGHT - MARGIN.bottom}
              className="chart-cursor"
            />
            <circle cx={selectedX} cy={observedY} r="4.5" className="chart-selected-point">
              <title>Selected observation: {formatPower(selected.observed_electrical_power_kw / 1000)}</title>
            </circle>
          </g>
        )}
        <text x={10} y={MARGIN.top + 6} className="chart-axis-label">MW</text>
      </svg>
      <div className="chart-footnote">
        Residual = synthetic observation − reference model · Screen: median absolute deviation
      </div>
    </div>
  )
}
