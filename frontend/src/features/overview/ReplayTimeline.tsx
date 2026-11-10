import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import type { ReactNode } from 'react'
import { CircleHelp, Pause, Play } from 'lucide-react'
import type { TimelinePoint } from '../../types'
import { formatUtcTime, powerMw, signedNumber } from '../../lib/format'
import { TimelineChart } from './TimelineChart'
import './ReplayTimeline.css'

export function ReplayTimeline({ timeline, selectedIndex, isPlaying, setPlaying, onSelect, title = 'Electrical output over 24 hours', description = 'Where does the observation depart from the reference?', children }: { timeline: TimelinePoint[]; selectedIndex: number; isPlaying: boolean; setPlaying: (value: boolean) => void; onSelect: (index: number) => void; title?: string; description?: string; children?: ReactNode }) {
  const liveRef = useRef<HTMLParagraphElement>(null)
  const [helpOpen, setHelpOpen] = useState(false)
  const [truthVisible, setTruthVisible] = useState(true)
  const count = timeline.length
  const flagged = timeline.some((row) => row.anomaly_flag)
  const selected = timeline[selectedIndex]
  useEffect(() => {
    if (isPlaying || !selected || !liveRef.current) return
    const timer = window.setTimeout(() => { if (liveRef.current) liveRef.current.textContent = `Sample ${selectedIndex + 1} of ${count}, ${formatUtcTime(selected.timestamp_utc)}.` }, 450)
    return () => window.clearTimeout(timer)
  }, [selectedIndex, count, isPlaying, selected])
  useEffect(() => {
    if (!isPlaying || count === 0) return
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const timer = window.setTimeout(() => {
      if (selectedIndex >= count - 1) setPlaying(false)
      else onSelect(selectedIndex + 1)
    }, reducedMotion ? 800 : 360)
    return () => window.clearTimeout(timer)
  }, [isPlaying, selectedIndex, count, onSelect, setPlaying])
  const jumpFlag = () => {
    const index = timeline.findIndex((row) => row.anomaly_flag)
    if (index >= 0) { onSelect(index); setPlaying(false) }
  }
  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    const formTarget = event.target instanceof HTMLInputElement || event.target instanceof HTMLButtonElement || event.target instanceof HTMLSelectElement
    if (formTarget && event.key.toLowerCase() !== 'f' && event.code !== 'Space') return
    let next: number | null = null
    if (event.key === 'ArrowLeft') next = selectedIndex - (event.shiftKey ? 10 : 1)
    else if (event.key === 'ArrowRight') next = selectedIndex + (event.shiftKey ? 10 : 1)
    else if (event.key === 'Home') next = 0
    else if (event.key === 'End') next = count - 1
    else if (event.key.toLowerCase() === 'f') { event.preventDefault(); if (flagged) jumpFlag(); return }
    else if (event.code === 'Space') { event.preventDefault(); setPlaying(!isPlaying); return }
    else return
    event.preventDefault()
    onSelect(Math.max(0, Math.min(count - 1, next)))
  }
  return (
    <section className="timeline-card panel" aria-labelledby="timeline-title" tabIndex={0} onKeyDown={onKeyDown}>
      <div className="timeline-heading"><div><h2 id="timeline-title">{title}</h2><p>{description}</p></div>
        <div className="timeline-actions"><button type="button" className="icon-action" aria-label="Replay keyboard shortcuts" aria-expanded={helpOpen} onClick={() => setHelpOpen((open) => !open)}><CircleHelp size={17} aria-hidden="true" /></button><button type="button" className="button button-quiet replay-button" onClick={() => setPlaying(!isPlaying)}>{isPlaying ? <Pause size={14} aria-hidden="true" /> : <Play size={14} aria-hidden="true" />}{isPlaying ? 'Pause replay' : 'Play replay'}</button></div>
      </div>
      {helpOpen && <div className="shortcut-popover" role="status"><strong>Replay keys</strong><span>Left / Right: one sample</span><span>Shift + Left / Right: ten samples</span><span>Home / End: first / last sample</span><span>Space: play or pause</span><span className={!flagged ? 'is-disabled' : ''}>F: first flagged sample{!flagged ? ' (none flagged)' : ''}</span></div>}
      {children ?? <TimelineChart timeline={timeline} selectedIndex={selectedIndex} truthVisible={truthVisible} onSelect={(index) => { setPlaying(false); onSelect(index) }} onToggleTruth={() => setTruthVisible((visible) => !visible)} />}
      <div className="timeline-scrubber-row"><label htmlFor="sample-range">Sample {selectedIndex + 1} of {count}</label><input id="sample-range" type="range" min="0" max={count - 1} value={selectedIndex} aria-label="Scenario sample" aria-valuetext={selected ? `Sample ${selectedIndex + 1} of ${count}; ${formatUtcTime(selected.timestamp_utc)} UTC; reference ${powerMw(selected.model_electrical_power_kw)} megawatts; observation ${powerMw(selected.observed_electrical_power_kw)} megawatts; residual ${signedNumber(selected.power_residual_kw / 1000)} megawatts` : 'No sample selected'} onKeyDown={(event) => { if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); onSelect(Math.max(0, Math.min(count - 1, selectedIndex + (event.key === 'ArrowLeft' ? -1 : 1) * (event.shiftKey ? 10 : 1)))) } }} onChange={(event) => { setPlaying(false); onSelect(Number(event.target.value)) }} /></div>
      <button className="first-flag-button" type="button" onClick={jumpFlag} disabled={!flagged}>First flagged sample</button>
      <p ref={liveRef} className="sr-only" aria-live="polite" aria-atomic="true">Sample {selectedIndex + 1} of {count}.</p>
    </section>
  )
}
