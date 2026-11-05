import { Suspense, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { OrbitControls } from '@react-three/drei'
import { Canvas } from '@react-three/fiber'
import { createPortal } from 'react-dom'
import { getPartPickerHost, getStageInfoHost, subscribePartPickerHost } from '../overview/partPickerHost'
import type { PartInspection, TurbineViewerProps } from './types'
import { useStageTokens, StageTokenContext } from './stageTokens'
import { SchematicTurbine } from './SchematicTurbine'
import { GLBModel } from './GLBModel'
import { ModelBoundary } from './ModelBoundary'
import { ViewerCameraReset } from './camera'
import { StageLights } from './lights'

const MODEL_PATH = '/models/turbine.glb'

export function TurbineViewer({ components, selectedComponentId, onSelectComponent, view, exploded, isolated, spinning, cameraKey, onModelStatus }: TurbineViewerProps) {
  const stageTokens = useStageTokens()
  const [modelUrl, setModelUrl] = useState<string | null>(null)
  const [modelName, setModelName] = useState<string | null>(null)
  const [modelFailed, setModelFailed] = useState(false)
  const [partCatalog, setPartCatalog] = useState<PartInspection[]>([])
  const [selectedPart, setSelectedPart] = useState<PartInspection | null>(null)
  const partPickerHost = useSyncExternalStore(subscribePartPickerHost, getPartPickerHost, () => null)
  const stageInfoHost = useSyncExternalStore(subscribePartPickerHost, getStageInfoHost, () => null)
  const previousComponentId = useRef(selectedComponentId)
  const preserveInspectedPartOnComponentChange = useRef(false)
  const modelInteractive = Boolean(modelUrl && !modelFailed)
  const activeSelectedPart = partCatalog.some((part) => part.objectId === selectedPart?.objectId)
    ? selectedPart
    : null

  useEffect(() => {
    let cancelled = false
    fetch(MODEL_PATH, { method: 'HEAD' })
      .then((response) => {
        const contentType = response.headers.get('content-type')?.split(';')[0].trim().toLowerCase()
        const isGlb = contentType === 'model/gltf-binary' || contentType === 'application/octet-stream'
        if (!cancelled && response.ok && isGlb) {
          setModelUrl(MODEL_PATH)
          setModelName('turbine.glb')
        } else if (!cancelled) {
          setModelFailed(true)
        }
      })
      .catch(() => { if (!cancelled) setModelFailed(true) })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    return () => {
      if (modelUrl?.startsWith('blob:')) URL.revokeObjectURL(modelUrl)
    }
  }, [modelUrl])

  useEffect(() => onModelStatus({ available: Boolean(modelUrl), failed: modelFailed }), [modelUrl, modelFailed, onModelStatus])

  useEffect(() => {
    if (previousComponentId.current === selectedComponentId) return
    previousComponentId.current = selectedComponentId
    if (preserveInspectedPartOnComponentChange.current) {
      preserveInspectedPartOnComponentChange.current = false
      return
    }
    setSelectedPart(null)
  }, [selectedComponentId])

  const selectComponent = (componentId: string) => {
    setSelectedPart(null)
    onSelectComponent(componentId)
  }

  const inspectPart = (part: PartInspection) => {
    setSelectedPart(part)
    preserveInspectedPartOnComponentChange.current = part.componentId !== selectedComponentId
    onSelectComponent(part.componentId)
  }

  return (
    <div className="viewer-scene">
      {partPickerHost && createPortal(
        <div className="part-browser">
          <label htmlFor="model-part-select">Model sub-parts Â· {components.find((component) => component.component_id === selectedComponentId)?.label ?? selectedComponentId}</label>
          <select id="model-part-select" value={activeSelectedPart?.componentId === selectedComponentId ? activeSelectedPart.objectId : ''} disabled={!modelInteractive || !partCatalog.some((part) => part.componentId === selectedComponentId)} onChange={(event) => {
            const part = partCatalog.find((candidate) => candidate.objectId === event.target.value)
            if (part) inspectPart(part)
          }}>
            <option value="">{modelInteractive ? 'Choose a mesh to inspect...' : 'Load the Blender model to inspect meshes...'}</option>
            {partCatalog.filter((part) => part.componentId === selectedComponentId).map((part) => <option key={part.objectId} value={part.objectId}>{part.name}{part.envelopeMm ? ` Â· ${part.envelopeMm}\u00a0mm single casting` : part.referenceEnvelopeMm ? ` Â· ${part.referenceEnvelopeMm}\u00a0mm stage reference` : ''}</option>)}
          </select>
        </div>,
        partPickerHost,
      )}
      <div className="viewer-stage">
        <Canvas
          dpr={[1, 1.5]}
          camera={{ position: [-6.4, -4.4, 7.6], fov: 35, near: 0.1, far: 100 }}
          gl={{ antialias: true, alpha: false }}
          role="img"
          aria-label="Interactive simplified gas turbine. Drag to orbit, right-drag to pan, scroll to zoom, and select a part to inspect it."
        >
          <color attach="background" args={[stageTokens.background]} />
          <StageLights tokens={stageTokens} />
          
          <StageTokenContext.Provider value={stageTokens}>
            <Suspense fallback={<SchematicTurbine components={components} selectedComponentId={selectedComponentId} onSelectComponent={selectComponent} />}>
              {modelUrl && view === 'glb' ? (
                <ModelBoundary
                  key={modelUrl}
                  onFailure={() => { setModelFailed(true); setPartCatalog([]) }}
                  fallback={<SchematicTurbine components={components} selectedComponentId={selectedComponentId} onSelectComponent={selectComponent} />}
                >
                  <GLBModel
                    url={modelUrl}
                    selectedComponentId={selectedComponentId}
                    selectedPart={activeSelectedPart}
                    isolated={isolated}
                    exploded={exploded}
                    spinning={spinning}
                    onSelectComponent={onSelectComponent}
                    onInspectPart={inspectPart}
                    onPartsAvailable={setPartCatalog}
                    selectedTone={stageTokens.selected}
                    stagePart={stageTokens.part}
                  />
                </ModelBoundary>
              ) : (
                <SchematicTurbine components={components} selectedComponentId={selectedComponentId} onSelectComponent={selectComponent} />
              )}
            </Suspense>
          </StageTokenContext.Provider>
          <OrbitControls enableDamping dampingFactor={0.08} enablePan panSpeed={0.9} zoomSpeed={0.8} rotateSpeed={0.8} minDistance={0.45} maxDistance={26} minPolarAngle={0.035} maxPolarAngle={Math.PI - 0.035} makeDefault />
          <ViewerCameraReset resetKey={cameraKey} />
        </Canvas>
        <div className="viewer-axis-label axis-intake">Air inlet</div>
        <div className="viewer-axis-label axis-core">Core</div>
        <div className="viewer-axis-label axis-output">Generator</div>
      </div>
      {stageInfoHost && createPortal(
        <>
          {modelFailed && <p className="viewer-fallback-note" role="status">The 3D model is unavailable; showing the interactive schematic.</p>}
          <div className="part-inspection" aria-live="polite">
            <div className="part-inspection-heading">
              <span className="part-inspection-label">Selected model part</span>
              {activeSelectedPart && <span className="part-component-tag">{activeSelectedPart.componentId.toUpperCase()}</span>}
            </div>
            {activeSelectedPart ? (
              <>
                <strong className="part-inspection-name">{activeSelectedPart.name}</strong>
                <div className="part-inspection-facts">
                  {activeSelectedPart.role && <span>{activeSelectedPart.role}</span>}
                  {activeSelectedPart.envelopeMm && <span>Single casting envelope: {activeSelectedPart.envelopeMm}{'\u00a0'}mm</span>}
                  {activeSelectedPart.massKg !== undefined && <span>Single casting listed mass: {activeSelectedPart.massKg}{'\u00a0'}kg</span>}
                  {activeSelectedPart.referenceLabel && <span>Related reference: {activeSelectedPart.referenceLabel}</span>}
                  {activeSelectedPart.referenceEnvelopeMm && <span>Stage casting envelope: {activeSelectedPart.referenceEnvelopeMm}{'\u00a0'}mm</span>}
                  {activeSelectedPart.referenceMassKg !== undefined && <span>Stage casting listed mass: {activeSelectedPart.referenceMassKg}{'\u00a0'}kg</span>}
                  {activeSelectedPart.instanceIndex !== undefined && activeSelectedPart.instanceCount !== undefined && <span>Visual instance {activeSelectedPart.instanceIndex} of {activeSelectedPart.instanceCount}</span>}
                </div>
                {activeSelectedPart.instanceCountNote && <div className="part-inspection-note">{activeSelectedPart.instanceCountNote}</div>}
                {activeSelectedPart.dataNote && <div className="part-inspection-note">{activeSelectedPart.dataNote}</div>}
                {activeSelectedPart.geometryNote && <div className="part-inspection-note">{activeSelectedPart.geometryNote}</div>}
                {activeSelectedPart.source && <a className="part-inspection-source" href={activeSelectedPart.source} target="_blank" rel="noreferrer">Open public source</a>}
              </>
            ) : <div className="part-inspection-empty">{modelInteractive ? 'Click any visible mesh in the Blender model to inspect the sub-part and available public metadata.' : 'Sub-part inspection is available when the Blender GLB is loaded.'}</div>}
            {spinning && <div className="visual-only-note">Rotor motion is illustrative only; it is not an RPM or operating-state prediction.</div>}
          </div>
          <div className="viewer-footnote">{modelName && !modelFailed ? `Loaded locally in this browser Â· ${modelName}` : 'No Blender export found in this workspace. The schematic is an interactive geometry scaffold.'}</div>
        </>,
        stageInfoHost,
      )}
    </div>
  )
}
