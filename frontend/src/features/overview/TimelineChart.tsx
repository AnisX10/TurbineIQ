import { useEffect, useRef, useState } from 'react'
import type { TimelinePoint } from '../../types'
import { formatUtcTime, numberText, signedNumber } from '../../lib/format'
import { ValueWithUnit } from '../../lib/ValueWithUnit'
import './TimelineChart.css'

export interface ChartSeries {
  key: string
  label: string
  values: Array<number | null>
  style: 'reference' | 'observation' | 'truth' | 'residual'
}

interface TimelineChartProps {
  timeline: TimelinePoint[]
  selectedIndex: number
  onSelect: (index: number) => void
  series?: ChartSeries[]
  unit?: string
  residualValues?: Array<number | null>
  showResidualStrip?: boolean
  zeroBaseline?: boolean
  truthVisible?: boolean
  onToggleTruth?: () => void
}

function flagShape(x: number, y: number): string {
  return `M ${x} ${y - 5} L ${x + 5} ${y + 4} L ${x - 5} ${y + 4} Z`
}

function chartNumber(value: number | null, unit: string): string {
  if (value === null || !Number.isFinite(value)) return '?'
  return numberText(value, unit === 'K' ? 1 : 2)
}

function validValues(series: ChartSeries[]): number[] {
  return series.flatMap((item) => item.values).filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
}

export function TimelineChart({ timeline, selectedIndex, onSelect, series: suppliedSeries, unit: suppliedUnit, residualValues, showResidualStrip: showResidualStripProp, zeroBaseline = false, truthVisible = true, onToggleTruth }: TimelineChartProps) {
  const host = useRef<HTMLDivElement>(null)
  const [measuredWidth, setMeasuredWidth] = useState(800)
  const [table, setTable] = useState(false)
  useEffect(() => {
    if (!host.current) return
    const observer = new ResizeObserver((entries) => setMeasuredWidth(Math.max(320, Math.floor(entries[0]?.contentRect.width ?? 800))))
    observer.observe(host.current)
    return () => observer.disconnect()
  }, [])
  const width = Math.max(measuredWidth, 620)
  const defaultSeries: ChartSeries[] = [
    { key: 'reference', label: 'Reference', style: 'reference', values: timeline.map((row) => row.model_electrical_power_kw / 1000) },
    ...(truthVisible ? [{ key: 'truth', label: 'Synthetic truth', style: 'truth' as const, values: timeline.map((row) => row.synthetic_truth_electrical_power_kw / 1000) }] : []),
    { key: 'observation', label: 'Observation', style: 'observation', values: timeline.map((row) => row.observed_electrical_power_kw / 1000) },
  ]
  const series = suppliedSeries ?? defaultSeries
  const unit = suppliedUnit ?? 'MW'
  const showResidualStrip = showResidualStripProp ?? suppliedSeries === undefined
  const residuals = residualValues ?? timeline.map((row) => row.power_residual_kw / 1000)
  const values = validValues(series)
  if (values.length === 0 || timeline.length === 0) return <div className="timeline-empty">No per-sample values are available for this metric.</div>
  const residualPresent = showResidualStrip ? residuals.filter((value): value is number => typeof value === 'number' && Number.isFinite(value)) : []
  const residualScale = Math.max(...residualPresent.map((value) => Math.abs(value)), 0.01)
  const min = Math.min(...values, ...(zeroBaseline ? [0] : []))
  const max = Math.max(...values, ...(zeroBaseline ? [0] : []))
  const span = Math.max(max - min, Math.abs(max) * 0.02, 0.02)
  const paddedMin = min - span * 0.08
  const paddedMax = max + span * 0.08
  const showStrip = showResidualStrip
  const height = showStrip ? 306 : 250
  const margin = { top: 20, right: 160, bottom: 36, left: 62 }
  const plotBottom = showStrip ? 214 : height - 40
  const residualTop = 236
  const plotWidth = width - margin.left - margin.right
  const x = (index: number) => margin.left + index / Math.max(timeline.length - 1, 1) * plotWidth
  const y = (value: number) => margin.top + (paddedMax - value) / (paddedMax - paddedMin) * (plotBottom - margin.top)
  const paths = series.map((item) => {
    const segments: string[] = []
    let current: string[] = []
    item.values.forEach((value, index) => {
      if (typeof value === 'number' && Number.isFinite(value)) current.push(`${x(index).toFixed(2)},${y(value).toFixed(2)}`)
      else if (current.length) { segments.push(current.join(' ')); current = [] }
    })
    if (current.length) segments.push(current.join(' '))
    const finalValue = [...item.values].reverse().find((value): value is number => typeof value === 'number' && Number.isFinite(value))
    const finalIndex = finalValue === undefined ? -1 : item.values.lastIndexOf(finalValue)
    return { ...item, segments, actualY: finalValue === undefined ? null : y(finalValue), finalX: finalIndex < 0 ? null : x(finalIndex), finalValue }
  })
  const labelGap = 19
  const labelMin = margin.top + 7
  const labelMax = plotBottom - 5
  const labelEntries = paths.filter((item) => item.actualY !== null).sort((a, b) => (a.actualY ?? 0) - (b.actualY ?? 0))
  const unshiftedLabels = labelEntries.reduce<Array<(typeof labelEntries)[number] & { labelY: number }>>((labels, item) => {
    const previousLabelY = labels.at(-1)?.labelY ?? labelMin - labelGap
    return [...labels, { ...item, labelY: Math.max(item.actualY ?? labelMin, previousLabelY + labelGap) }]
  }, [])
  const labelShift = Math.max(0, (unshiftedLabels.at(-1)?.labelY ?? labelMin) - labelMax)
  const directLabels = unshiftedLabels.map((item) => ({ ...item, labelY: item.labelY - labelShift }))
  const selected = timeline[selectedIndex]
  const selectedSeries = series.find((item) => item.style === 'observation') ?? series[0]
  const selectedValue = selectedSeries?.values[selectedIndex] ?? null
  const selectedY = typeof selectedValue === 'number' ? y(selectedValue) : margin.top
  const selectedX = x(selectedIndex)
  const chipX = Math.max(170, Math.min(width - 170, selectedX))
  const chipY = selectedY < 68 ? selectedY + 14 : selectedY - 9
  const flaggedCount = timeline.filter((row) => row.anomaly_flag).length
  const peakResidual = Math.max(...residualPresent.map((value) => Math.abs(value)), 0)
  const trend = showStrip
    ? flaggedCount > 0
      ? `${flaggedCount} of ${timeline.length} samples are flagged by the residual screen; the selected observation is ${selected?.power_residual_kw < 0 ? 'below' : 'above'} the reference model.`
      : `No samples are flagged by the residual screen; the largest absolute residual is ${peakResidual.toFixed(2)} ${unit}.`
    : `The selected series ranges from ${Math.min(...values).toFixed(unit === 'K' ? 1 : 2)} to ${Math.max(...values).toFixed(unit === 'K' ? 1 : 2)} ${unit} across ${timeline.length} synthetic samples.`

  return (
    <div className="timeline-chart" ref={host}>
      <div className="timeline-chart-controls">
        {suppliedSeries === undefined && onToggleTruth && <button type="button" className={`text-control ${truthVisible ? 'is-on' : ''}`} aria-pressed={truthVisible} onClick={onToggleTruth}>Synthetic truth {truthVisible ? 'shown' : 'hidden'}</button>}
        <button type="button" className="text-control" aria-pressed={table} onClick={() => setTable((value) => !value)}>{table ? 'View chart' : 'View as table'}</button>
      </div>
      {table ? (
        <div className="timeline-table-wrap"><table className="timeline-table"><thead><tr><th>Time (UTC)</th>{series.map((item) => <th key={item.key}>{item.label} ({unit})</th>)}{residualValues && <th>Residual ({unit})</th>}{showStrip && <th>Screen</th>}</tr></thead><tbody>{timeline.map((row, index) => <tr key={row.timestamp_utc} className={index === selectedIndex ? 'is-selected' : ''}><td><button type="button" className="timeline-table-select" aria-label={`Select sample ${index + 1}, ${formatUtcTime(row.timestamp_utc)}`} onClick={() => onSelect(index)}>{formatUtcTime(row.timestamp_utc)}<span className="sr-only">, sample {index + 1}</span></button></td>{series.map((item) => <td key={item.key}>{chartNumber(item.values[index] ?? null, unit)}</td>)}{residualValues && <td className={residualValues[index] === 0 ? 'zero-value' : ''}>{residualValues[index] === null || residualValues[index] === undefined ? '?' : signedNumber(residualValues[index], unit === 'K' ? 1 : 2)}</td>}{showStrip && <td>{row.anomaly_flag ? 'Flagged by residual screen' : 'Not flagged'}</td>}</tr>)}</tbody></table></div>
      ) : (
        <div className="chart-scroll" role="region" aria-label="Scrollable chart plot" tabIndex={0}><div className="chart-canvas" style={{ width }}><svg className="responsive-chart-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${series.map((item) => item.label).join(', ')} across the synthetic timeline`}>
          {Array.from({ length: 5 }, (_, index) => {
            const value = paddedMax - (paddedMax - paddedMin) * index / 4
            const yy = margin.top + (plotBottom - margin.top) * index / 4
            return <g key={value}><line x1={margin.left} x2={width - margin.right} y1={yy} y2={yy} className="chart-grid" /><text x={margin.left - 9} y={yy + 4} textAnchor="end" className="chart-axis-label">{value.toFixed(unit === 'K' ? 1 : 2)}</text></g>
          })}
          <text x="10" y={margin.top - 8} className="chart-axis-label">{unit}</text>
          <line x1={margin.left} x2={width - margin.right} y1={plotBottom} y2={plotBottom} className="chart-axis-line" />
          {zeroBaseline && paddedMin <= 0 && paddedMax >= 0 && <line x1={margin.left} x2={width - margin.right} y1={y(0)} y2={y(0)} className="residual-zero" />}
          <text x={margin.left} y={plotBottom + 19} className="chart-axis-label">{formatUtcTime(timeline[0]?.timestamp_utc)}</text>
          <text x={width - margin.right} y={plotBottom + 19} textAnchor="end" className="chart-axis-label">{formatUtcTime(timeline.at(-1)?.timestamp_utc)}</text>
          {paths.map((item) => item.segments.map((points, index) => <polyline key={`${item.key}-${index}`} points={points} className={`timeline-line line-${item.style}`} fill="none" />))}
          {directLabels.map((item) => item.finalX !== null && item.actualY !== null && <g key={`${item.key}-label`} className={`direct-${item.style}`}><path d={`M ${item.finalX} ${item.actualY} L ${width - margin.right + 5} ${item.labelY}`} className="direct-label-connector" /><text x={width - margin.right + 9} y={item.labelY + 4} className="direct-label">{item.label}</text></g>)}
          {selected && typeof selectedValue === 'number' && <g><line x1={selectedX} x2={selectedX} y1={margin.top} y2={plotBottom} className="chart-playhead" /><circle cx={selectedX} cy={selectedY} r="4" className="chart-selected-point" /></g>}
          {showStrip && <>
            <text x="10" y={residualTop + 9} className="chart-axis-label">Residual ? {unit}</text>
            <text x={margin.left - 9} y={residualTop + 11} textAnchor="end" className="chart-axis-label">+{residualScale.toFixed(unit === 'K' ? 1 : 2)}</text>
            <text x={margin.left - 9} y={residualTop + 33} textAnchor="end" className="chart-axis-label">0.00</text>
            <text x={margin.left - 9} y={residualTop + 54} textAnchor="end" className="chart-axis-label">?{residualScale.toFixed(unit === 'K' ? 1 : 2)}</text>
            {timeline.map((row, index) => {
              const value = residuals[index]
              if (typeof value !== 'number' || !Number.isFinite(value)) return null
              const zeroY = residualTop + 34
              const yy = zeroY - value / residualScale * 22
              return <g key={`residual-${index}`}><line x1={x(index)} x2={x(index)} y1={zeroY} y2={yy} className={`residual-mark ${row.anomaly_flag ? 'is-flagged' : ''}`} />{row.anomaly_flag && <path d={flagShape(x(index), yy)} className="flag-marker"><title>Flagged by residual screen, sample {index + 1}</title></path>}</g>
            })}
            <line x1={margin.left} x2={width - margin.right} y1={residualTop + 34} y2={residualTop + 34} className="residual-zero" />
            {selected && <line x1={selectedX} x2={selectedX} y1={residualTop} y2={height - 10} className="chart-playhead" />}
            <text x={margin.left} y={height - 1} className="chart-axis-label">{formatUtcTime(timeline[0]?.timestamp_utc)}</text>
            <text x={width - margin.right} y={height - 1} textAnchor="end" className="chart-axis-label">{formatUtcTime(timeline.at(-1)?.timestamp_utc)}</text>
          </>}
        </svg>{selected && <div className="chart-playhead-readout" style={{ left: chipX, top: chipY }}>{formatUtcTime(selected.timestamp_utc)} UTC{series.map((item) => <span key={item.key}>{item.label} {chartNumber(item.values[selectedIndex] ?? null, unit)} {unit}</span>)}</div>}</div></div>
      )}
      <p className="trend-summary">{trend}</p>
      {selected && <div className="chart-readout" aria-label="Selected sample readout"><span>{formatUtcTime(selected.timestamp_utc)}</span>{series.map((item) => <span key={item.key}>{item.label} <ValueWithUnit value={chartNumber(item.values[selectedIndex] ?? null, unit)} unit={unit} /></span>)}{residualValues && <span>Residual <ValueWithUnit value={residualValues[selectedIndex] === null || residualValues[selectedIndex] === undefined ? '?' : signedNumber(residualValues[selectedIndex], unit === 'K' ? 1 : 2)} unit={unit} /></span>}</div>}
    </div>
  )
}
