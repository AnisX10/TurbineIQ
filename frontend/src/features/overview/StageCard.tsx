import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { Expand, Focus, RotateCcw, RotateCw } from 'lucide-react'
import type { TwinComponentState } from '../../types'
import { setStageInfoHost } from './partPickerHost'
import './StageCard.css'

const TurbineCanvas = lazy(() => import('../../TurbineViewer').then((module) => ({ default: module.TurbineViewer })))

type StageView = 'glb' | 'schematic'

interface ModelStatus {
  available: boolean
  failed: boolean
}

function StagePreview() {
  return (
    <div className="stage-preview" role="img" aria-label="Simplified gas turbine schematic loading">
      <svg viewBox="0 0 640 480" aria-hidden="true">
        <path d="M72 240h496" className="preview-shaft" />
        <path d="M95 188h138l34 52-34 52H95z" className="preview-component" />
        <path d="M278 201h89l24 39-24 39h-89l-24-39z" className="preview-component" />
        <path d="M402 181h104l31 59-31 59H402l-24-59z" className="preview-component" />
        <path d="M113 212h105m72 0h65m58-1h90" className="preview-detail" />
        <text x="164" y="365">COMPRESSOR</text><text x="324" y="365">COMBUSTOR</text><text x="458" y="365">TURBINE</text>
      </svg>
      <span>Loading interactive Stage</span>
    </div>
  )
}

export function StageCard({ components, selectedComponentId, onSelectComponent, active }: { components: TwinComponentState[]; selectedComponentId: string; onSelectComponent: (id: string) => void; active: boolean }) {
  const viewportRef = useRef<HTMLDivElement>(null)
  const [view, setView] = useState<StageView>('glb')
  const [model, setModel] = useState<ModelStatus>({ available: false, failed: false })
  const [exploded, setExploded] = useState(false)
  const [isolated, setIsolated] = useState(false)
  const [spinning, setSpinning] = useState(false)
  const [cameraKey, setCameraKey] = useState(0)
  const [canvasReady, setCanvasReady] = useState(false)
  const [reduceMotion, setReduceMotion] = useState(() => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  useEffect(() => {
    if (!active) return
    const viewport = viewportRef.current
    if (!viewport) return
    const idleWindow = window as Window & {
      requestIdleCallback?: (callback: () => void, options?: { timeout: number }) => number
      cancelIdleCallback?: (handle: number) => void
    }
    let idleHandle: number | null = null
    let timeoutHandle: number | null = null
    let idleScheduled = false
    let activated = false
    const cancelPendingActivation = () => {
      if (idleHandle !== null) idleWindow.cancelIdleCallback?.(idleHandle)
      if (timeoutHandle !== null) window.clearTimeout(timeoutHandle)
      idleHandle = null
      timeoutHandle = null
      idleScheduled = false
    }
    const activate = () => {
      idleHandle = null
      timeoutHandle = null
      idleScheduled = false
      if (activated) return
      activated = true
      setCanvasReady(true)
      observer.disconnect()
    }
    const scheduleActivation = () => {
      if (activated || idleScheduled) return
      idleScheduled = true
      if (idleWindow.requestIdleCallback) idleHandle = idleWindow.requestIdleCallback(activate, { timeout: 1000 })
      else timeoutHandle = window.setTimeout(activate, 0)
    }
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) scheduleActivation()
      else if (!activated) cancelPendingActivation()
    }, { rootMargin: '80px' })
    observer.observe(viewport)
    return () => {
      observer.disconnect()
      cancelPendingActivation()
    }
  }, [active])
  useEffect(() => {
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => { setReduceMotion(preference.matches); if (preference.matches) setSpinning(false) }
    update()
    preference.addEventListener('change', update)
    return () => preference.removeEventListener('change', update)
  }, [])
  const modelInteractive = model.available && !model.failed
  const controls = [
    { label: 'Reset camera', icon: RotateCcw, onClick: () => setCameraKey((key) => key + 1), pressed: false, disabled: false },
    { label: exploded ? 'Reassemble model' : 'Explode view', icon: Expand, onClick: () => setExploded((value) => !value), pressed: exploded, disabled: !modelInteractive },
    { label: isolated ? 'Show all parts' : 'Isolate component', icon: Focus, onClick: () => setIsolated((value) => !value), pressed: isolated, disabled: !modelInteractive },
    { label: spinning ? 'Pause rotor motion' : 'Rotor motion', icon: RotateCw, onClick: () => setSpinning((value) => !value), pressed: spinning, disabled: !modelInteractive || reduceMotion },
  ]

  return (
    <section className="viewer-panel panel" aria-labelledby="stage-title">
      <div className="viewer-heading"><div><h2 id="stage-title">Stage</h2><p>GE 6B.03 · simplified reference</p></div><span className="model-state" role="status">{model.failed ? 'Schematic fallback' : modelInteractive ? 'Blender GLB' : active ? 'Loading local GLB' : 'Preparing synthetic run'}</span></div>
      <div className="stage-toolbar" role="group" aria-label="Stage controls">
        <div className="stage-segmented" role="group" aria-label="Stage view">
          <button type="button" aria-pressed={view === 'glb'} disabled={!modelInteractive} onClick={() => setView('glb')}>GLB</button>
          <button type="button" aria-label="Schematic" aria-pressed={view === 'schematic'} onClick={() => setView('schematic')}><span className="stage-schematic-full">Schematic</span><span className="stage-schematic-short">Schem.</span></button>
        </div>
        {controls.map(({ label, icon: Icon, onClick, pressed, disabled }) => <button key={label} type="button" className="stage-icon-button" aria-label={label} aria-pressed={pressed} aria-disabled={disabled} data-tooltip={label} onClick={(event) => { if (disabled) { event.preventDefault(); return } onClick() }}><Icon size={17} strokeWidth={1.8} aria-hidden="true" /><span className="sr-only">{label}</span></button>)}
      </div>
      <div className="stage-viewport" ref={viewportRef}>
        {canvasReady ? <Suspense fallback={<StagePreview />}>
          <TurbineCanvas components={components} selectedComponentId={selectedComponentId} onSelectComponent={onSelectComponent} view={view} exploded={exploded} isolated={isolated} spinning={spinning} cameraKey={cameraKey} onModelStatus={setModel} />
        </Suspense> : <StagePreview />}
        <div className="viewer-note">Orbit with drag. Pan with right-drag. Zoom with scroll. Click a part to inspect.</div>
      </div>
      <div className="stage-info-slot" ref={setStageInfoHost} />
    </section>
  )
}
