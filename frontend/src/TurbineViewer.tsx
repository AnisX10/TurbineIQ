import { Component, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { OrbitControls, useGLTF } from '@react-three/drei'
import { Canvas, useFrame, useThree, type ThreeEvent } from '@react-three/fiber'
import {
  Box3,
  Color,
  Group,
  Mesh,
  MeshStandardMaterial,
  PerspectiveCamera,
  Sphere,
  Vector3,
} from 'three'
import type { Object3D } from 'three'
import type { TwinComponentState } from './types'

const MODEL_PATH = '/models/turbine.glb'
const SELECTED_TONE = '#56d0db'

interface TurbineViewerProps {
  components: TwinComponentState[]
  selectedComponentId: string
  onSelectComponent: (componentId: string) => void
}

interface PartInspection {
  componentId: string
  objectId: string
  name: string
  role?: string
  envelopeMm?: string
  massKg?: number
  referenceLabel?: string
  referenceEnvelopeMm?: string
  referenceMassKg?: number
  dataNote?: string
  source?: string
  geometryNote?: string
  instanceIndex?: number
  instanceCount?: number
  instanceCountNote?: string
}

const EXPLODED_OFFSETS: Record<string, [number, number, number]> = {
  inlet: [-0.7, 0, 0],
  compressor: [-0.1, 0.18, 0.22],
  combustor: [0, 0.82, 0.66],
  turbine: [0.35, -0.12, 0.26],
  shaft: [0, -0.78, -0.54],
  generator: [0.92, 0, 0],
}

interface PartProps {
  id: string
  position?: [number, number, number]
  outlineRadius?: number
  selected: boolean
  status: string
  onSelect: (componentId: string) => void
  children: ReactNode
}

function toneForStatus(status: string): string {
  if (status === 'scenario_perturbation') return '#bd8b4f'
  if (status === 'residual_screen' || status === 'synthetic_measurement_fault') return '#b76e60'
  if (status === 'scenario_context') return '#5b8f9b'
  return '#607681'
}

function Part({ id, position, outlineRadius = 0.66, selected, status, onSelect, children }: PartProps) {
  const baseTone = toneForStatus(status)
  const onClick = (event: ThreeEvent<MouseEvent>) => {
    event.stopPropagation()
    onSelect(id)
  }
  const onPointerOver = (event: ThreeEvent<PointerEvent>) => {
    event.stopPropagation()
    document.body.style.cursor = 'pointer'
  }
  const onPointerOut = () => {
    document.body.style.cursor = 'default'
  }

  return (
    <group
      position={position}
      onClick={onClick}
      onPointerOver={onPointerOver}
      onPointerOut={onPointerOut}
      userData={{ turbineiqComponentId: id }}
    >
      {children}
      <mesh rotation={[0, Math.PI / 2, 0]}>
        <torusGeometry args={[outlineRadius, selected ? 0.035 : 0.02, 8, 48]} />
        <meshStandardMaterial
          color={selected ? SELECTED_TONE : baseTone}
          emissive={selected ? SELECTED_TONE : '#000000'}
          emissiveIntensity={selected ? 0.18 : 0}
          metalness={0.62}
          roughness={0.43}
          transparent={status !== 'nominal' && !selected}
          opacity={status !== 'nominal' && !selected ? 0.78 : 1}
        />
      </mesh>
    </group>
  )
}

function AxialCylinder({
  x,
  length,
  radius,
  color,
  opacity = 1,
}: {
  x: number
  length: number
  radius: number
  color: string
  opacity?: number
}) {
  return (
    <mesh position={[x, 0, 0]} rotation={[0, 0, Math.PI / 2]} castShadow receiveShadow>
      <cylinderGeometry args={[radius, radius, length, 48, 1, false]} />
      <meshStandardMaterial
        color={color}
        metalness={0.68}
        roughness={0.37}
        transparent={opacity < 1}
        opacity={opacity}
        depthWrite={opacity >= 1}
      />
    </mesh>
  )
}

function Ring({ x, radius, color = '#8295a0' }: { x: number; radius: number; color?: string }) {
  return (
    <mesh position={[x, 0, 0]} rotation={[0, Math.PI / 2, 0]}>
      <torusGeometry args={[radius, 0.025, 10, 48]} />
      <meshStandardMaterial color={color} metalness={0.78} roughness={0.3} />
    </mesh>
  )
}

function BladeRow({ x, count, radius, color }: { x: number; count: number; radius: number; color: string }) {
  return (
    <group position={[x, 0, 0]}>
      {Array.from({ length: count }, (_, index) => {
        const angle = (index / count) * Math.PI * 2
        return (
          <mesh
            key={index}
            position={[0, Math.cos(angle) * radius, Math.sin(angle) * radius]}
            rotation={[angle, 0, angle * 0.18]}
            castShadow
          >
            <boxGeometry args={[0.055, radius * 1.1, 0.035]} />
            <meshStandardMaterial color={color} metalness={0.8} roughness={0.32} />
          </mesh>
        )
      })}
      <mesh rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.16, 0.16, 0.08, 32]} />
        <meshStandardMaterial color="#9aaab0" metalness={0.82} roughness={0.28} />
      </mesh>
    </group>
  )
}

function SchematicTurbine({
  components,
  selectedComponentId,
  onSelectComponent,
}: TurbineViewerProps) {
  const statusById = new Map(components.map((component) => [component.component_id, component.status]))
  const selected = (id: string) => selectedComponentId === id
  const status = (id: string) => statusById.get(id) ?? 'nominal'

  return (
    <group position={[-0.15, 0.05, 0]}>
      <Part id="inlet" position={[-4.05, 0, 0]} outlineRadius={0.45} selected={selected('inlet')} status={status('inlet')} onSelect={onSelectComponent}>
        <AxialCylinder x={0} length={0.8} radius={0.43} color="#435660" />
        <Ring x={-0.33} radius={0.43} />
        <Ring x={0.33} radius={0.43} />
      </Part>
      <Part id="compressor" position={[-2.3, 0, 0]} outlineRadius={0.72} selected={selected('compressor')} status={status('compressor')} onSelect={onSelectComponent}>
        <AxialCylinder x={0} length={1.75} radius={0.7} color="#34444d" opacity={0.36} />
        {[-0.78, -0.39, 0, 0.39, 0.78].map((x) => <Ring key={x} x={x} radius={0.65} />)}
        {[-0.62, -0.22, 0.18, 0.58].map((x) => (
          <BladeRow key={x} x={x} count={10} radius={0.5} color="#8da0a6" />
        ))}
        <AxialCylinder x={0} length={1.6} radius={0.15} color="#9daeb4" />
      </Part>
      <Part id="combustor" position={[-0.25, 0, 0]} outlineRadius={0.56} selected={selected('combustor')} status={status('combustor')} onSelect={onSelectComponent}>
        <AxialCylinder x={0} length={1.15} radius={0.54} color="#765c44" opacity={0.7} />
        <AxialCylinder x={0} length={0.82} radius={0.34} color="#b97843" opacity={0.8} />
        {[-0.48, 0.48].map((x) => <Ring key={x} x={x} radius={0.52} color="#d49b61" />)}
      </Part>
      <Part id="turbine" position={[1.35, 0, 0]} outlineRadius={0.74} selected={selected('turbine')} status={status('turbine')} onSelect={onSelectComponent}>
        <AxialCylinder x={0} length={1.45} radius={0.72} color="#34444d" opacity={0.36} />
        {[-0.66, -0.22, 0.22, 0.66].map((x) => <Ring key={x} x={x} radius={0.68} />)}
        {[-0.45, 0, 0.45].map((x) => (
          <BladeRow key={x} x={x} count={12} radius={0.54} color="#9caeb3" />
        ))}
        <AxialCylinder x={0} length={1.3} radius={0.17} color="#9daeb4" />
      </Part>
      <Part id="shaft" position={[0.15, -0.02, 0]} outlineRadius={0.12} selected={selected('shaft')} status={status('shaft')} onSelect={onSelectComponent}>
        <AxialCylinder x={0} length={6.35} radius={0.095} color="#7d929a" />
      </Part>
      <Part id="generator" position={[4.12, 0, 0]} outlineRadius={0.6} selected={selected('generator')} status={status('generator')} onSelect={onSelectComponent}>
        <AxialCylinder x={0} length={1.4} radius={0.58} color="#465760" />
        {[-0.52, -0.27, 0, 0.27, 0.52].map((x) => <Ring key={x} x={x} radius={0.58} color="#8699a0" />)}
        <AxialCylinder x={0.82} length={0.3} radius={0.38} color="#3d4d55" />
      </Part>
      <gridHelper args={[12, 24, '#31414c', '#1d2a34']} position={[0, -1.08, 0]} />
    </group>
  )
}

const COMPONENT_ALIASES: Record<string, string[]> = {
  inlet: ['inlet', 'intake', 'air_entry'],
  compressor: ['compressor', 'comp_stage', 'compressor_casing'],
  combustor: ['combustor', 'combustion', 'combustion_chamber'],
  turbine: ['turbine', 'turbine_stage', 'turbine_casing'],
  shaft: ['shaft', 'rotor', 'spool'],
  generator: ['generator', 'alternator'],
}

function normalizeComponentId(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const normalized = value.toLowerCase().replaceAll(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')
  for (const [componentId, aliases] of Object.entries(COMPONENT_ALIASES)) {
    if (componentId === normalized || aliases.includes(normalized)) return componentId
  }
  return null
}

function inspectObject(object: Object3D, componentId: string): PartInspection {
  const metadata = object.userData as Record<string, unknown>
  const name = object.name || 'Unnamed model part'
  return {
    componentId,
    objectId: `${componentId}:${name}`,
    name: name.replaceAll('_', ' ').replaceAll(/\s*\|\s*/g, ' · ').replaceAll(/\s+/g, ' ').trim(),
    role: typeof metadata.row_role === 'string' ? metadata.row_role : undefined,
    envelopeMm: typeof metadata.public_component_envelope_mm === 'string'
      ? metadata.public_component_envelope_mm
      : undefined,
    massKg: typeof metadata.public_component_mass_kg === 'number'
      ? metadata.public_component_mass_kg
      : undefined,
    referenceLabel: typeof metadata.public_reference_label === 'string'
      ? metadata.public_reference_label
      : undefined,
    referenceEnvelopeMm: typeof metadata.public_reference_envelope_mm === 'string'
      ? metadata.public_reference_envelope_mm
      : undefined,
    referenceMassKg: typeof metadata.public_reference_mass_kg === 'number'
      ? metadata.public_reference_mass_kg
      : undefined,
    dataNote: typeof metadata.envelope_note === 'string'
      ? metadata.envelope_note
      : typeof metadata.reference_note === 'string'
        ? metadata.reference_note
        : undefined,
    source: typeof metadata.envelope_source === 'string'
      ? metadata.envelope_source
      : typeof metadata.reference_source === 'string'
        ? metadata.reference_source
        : undefined,
    geometryNote: typeof metadata.geometry_accuracy === 'string' ? metadata.geometry_accuracy : undefined,
    instanceIndex: typeof metadata.row_instance_index === 'number' ? metadata.row_instance_index : undefined,
    instanceCount: typeof metadata.row_instance_count === 'number' ? metadata.row_instance_count : undefined,
    instanceCountNote: typeof metadata.row_instance_count_note === 'string'
      ? metadata.row_instance_count_note
      : undefined,
  }
}

function partIdFor(object: Object3D, componentId: string | null): string | null {
  return componentId ? `${componentId}:${object.name || object.uuid}` : null
}

function normalizedObjectName(name: string): string {
  return name.toLowerCase().replaceAll(/[^a-z0-9]+/g, ' ').replaceAll(/\s+/g, ' ').trim()
}

function isRotorPart(object: Object3D): boolean {
  const name = normalizedObjectName(object.name)
  return name === 'main rotor shaft'
    || name.startsWith('compressor rotor stage')
    || name.startsWith('compressor rotor disk rim')
    || (name.startsWith('stage ')
      && (name.includes('bucket casting proxy')
        || name.includes('rotating buckets')
        || name.includes('rotor wheel')))
}

interface ViewerControls {
  reset: () => void
  target: Vector3
  update: () => void
}

function ViewerCameraReset({ resetKey }: { resetKey: number }) {
  const controls = useThree((state) => state.controls as unknown as ViewerControls | null)
  useEffect(() => {
    if (resetKey > 0) controls?.reset()
  }, [controls, resetKey])
  return null
}

function componentIdFor(object: Object3D): string | null {
  let current: Object3D | null = object
  while (current) {
    const metadata = current.userData as Record<string, unknown>
    const customId = normalizeComponentId(metadata.component_id ?? metadata.componentId)
    if (customId) return customId
    const byName = normalizeComponentId(current.name)
    if (byName) return byName
    for (const [componentId, aliases] of Object.entries(COMPONENT_ALIASES)) {
      if (aliases.some((alias) => current?.name.toLowerCase().includes(alias))) return componentId
    }
    current = current.parent
  }
  return null
}

function GLBModel({
  url,
  selectedComponentId,
  selectedPart,
  isolated,
  exploded,
  spinning,
  onSelectComponent,
  onInspectPart,
  onPartsAvailable,
}: {
  url: string
  selectedComponentId: string
  selectedPart: PartInspection | null
  isolated: boolean
  exploded: boolean
  spinning: boolean
  onSelectComponent: (componentId: string) => void
  onInspectPart: (part: PartInspection) => void
  onPartsAvailable: (parts: PartInspection[]) => void
}) {
  const gltf = useGLTF(url)
  const camera = useThree((state) => state.camera)
  const controls = useThree((state) => state.controls as unknown as ViewerControls | null)
  const fittedScene = useMemo(() => {
    const scene = gltf.scene.clone(true)
    scene.traverse((object) => {
      const metadata = object.userData as Record<string, unknown>
      if (typeof metadata.component_id === 'string') {
        object.userData.turbineiqBasePosition = object.position.toArray()
      }
      if (object instanceof Mesh) {
        object.userData.turbineiqComponentId = componentIdFor(object)
        object.material = Array.isArray(object.material)
          ? object.material.map((material) => material.clone())
          : object.material.clone()
        object.castShadow = true
        object.receiveShadow = true
      }
    })
    const wrapper = new Group()
    wrapper.add(scene)
    const bounds = new Box3().setFromObject(wrapper)
    const size = bounds.getSize(new Vector3())
    const center = bounds.getCenter(new Vector3())
    scene.position.sub(center)
    wrapper.scale.setScalar(8.6 / Math.max(size.x, size.y, size.z, 0.001))
    return wrapper
  }, [gltf.scene])
  const rotorParts = useMemo(() => {
    const parts: Object3D[] = []
    fittedScene.traverse((object) => {
      if (isRotorPart(object)) parts.push(object)
    })
    return parts
  }, [fittedScene])
  const partCatalog = useMemo(() => {
    const parts: PartInspection[] = []
    fittedScene.traverse((object) => {
      if (!(object instanceof Mesh)) return
      const componentId = componentIdFor(object)
      if (componentId) parts.push(inspectObject(object, componentId))
    })
    return parts
  }, [fittedScene])

  useEffect(() => {
    onPartsAvailable(partCatalog)
  }, [onPartsAvailable, partCatalog])

  useEffect(() => {
    fittedScene.traverse((object) => {
      const metadata = object.userData as Record<string, unknown>
      const componentId = normalizeComponentId(metadata.component_id)
      if (componentId) {
        const basePosition = metadata.turbineiqBasePosition
        if (Array.isArray(basePosition) && basePosition.length === 3) {
          object.position.set(Number(basePosition[0]), Number(basePosition[1]), Number(basePosition[2]))
        }
        if (exploded) {
          const offset = EXPLODED_OFFSETS[componentId]
          if (offset) object.position.add(new Vector3(...offset))
        }
      }
      if (!(object instanceof Mesh)) return
      const objectComponentId = componentIdFor(object)
      const objectId = partIdFor(object, objectComponentId)
      object.visible = !isolated
        || (selectedPart ? objectId === selectedPart.objectId : objectComponentId === selectedComponentId)
      const selected = objectComponentId === selectedComponentId
      const selectedPartMesh = selectedPart?.objectId === objectId
      const materials = Array.isArray(object.material) ? object.material : [object.material]
      materials.forEach((material) => {
        if (material instanceof MeshStandardMaterial) {
          material.emissive = new Color(selectedPartMesh ? '#9af4e8' : selected ? SELECTED_TONE : '#000000')
          material.emissiveIntensity = selectedPartMesh ? 0.48 : selected ? 0.16 : 0
        }
      })
    })
  }, [exploded, fittedScene, isolated, selectedComponentId, selectedPart])

  useEffect(() => {
    if (!isolated || !controls) return
    fittedScene.updateMatrixWorld(true)
    const visibleBounds = new Box3()
    fittedScene.traverse((object) => {
      if (object instanceof Mesh && object.visible) visibleBounds.expandByObject(object)
    })
    if (visibleBounds.isEmpty()) return

    const sphere = visibleBounds.getBoundingSphere(new Sphere())
    const direction = camera.position.clone().sub(controls.target)
    if (direction.lengthSq() < 1e-8) direction.set(-6.4, -4.4, 7.6)
    direction.normalize()
    const fov = camera instanceof PerspectiveCamera ? camera.fov : 35
    const distance = Math.max(sphere.radius / Math.sin((fov * Math.PI) / 360) * 1.35, 0.45)
    camera.position.copy(sphere.center).addScaledVector(direction, distance)
    controls.target.copy(sphere.center)
    controls.update()
  }, [camera, controls, exploded, fittedScene, isolated, selectedComponentId, selectedPart])

  useFrame((_, delta) => {
    if (!spinning) return
    const step = Math.min(delta, 0.05) * 4.2
    rotorParts.forEach((object) => { object.rotation.x += step })
  })

  return (
    <primitive
      object={fittedScene}
      onClick={(event: ThreeEvent<MouseEvent>) => {
        const componentId = componentIdFor(event.object)
        if (componentId) {
          event.stopPropagation()
          onSelectComponent(componentId)
          onInspectPart(inspectObject(event.object, componentId))
        }
      }}
    />
  )
}

interface ModelBoundaryProps {
  children: ReactNode
  fallback: ReactNode
  onFailure: () => void
}

interface ModelBoundaryState {
  failed: boolean
}

class ModelBoundary extends Component<ModelBoundaryProps, ModelBoundaryState> {
  state: ModelBoundaryState = { failed: false }

  static getDerivedStateFromError(): ModelBoundaryState {
    return { failed: true }
  }

  componentDidCatch(_error: Error, _info: ErrorInfo) {
    this.props.onFailure()
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

export function TurbineViewer({ components, selectedComponentId, onSelectComponent }: TurbineViewerProps) {
  const [modelUrl, setModelUrl] = useState<string | null>(null)
  const [modelName, setModelName] = useState<string | null>(null)
  const [modelFailed, setModelFailed] = useState(false)
  const [partCatalog, setPartCatalog] = useState<PartInspection[]>([])
  const [selectedPart, setSelectedPart] = useState<PartInspection | null>(null)
  const [exploded, setExploded] = useState(false)
  const [isolated, setIsolated] = useState(false)
  const [spinning, setSpinning] = useState(() => !window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  const [cameraKey, setCameraKey] = useState(0)
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
        }
      })
      .catch(() => undefined)
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    return () => {
      if (modelUrl?.startsWith('blob:')) URL.revokeObjectURL(modelUrl)
    }
  }, [modelUrl])

  useEffect(() => {
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)')
    const stopForReducedMotion = () => {
      if (preference.matches) setSpinning(false)
    }
    preference.addEventListener('change', stopForReducedMotion)
    return () => preference.removeEventListener('change', stopForReducedMotion)
  }, [])

  useEffect(() => {
    if (previousComponentId.current === selectedComponentId) return
    previousComponentId.current = selectedComponentId
    if (preserveInspectedPartOnComponentChange.current) {
      preserveInspectedPartOnComponentChange.current = false
      return
    }
    setSelectedPart(null)
  }, [selectedComponentId])

  const onFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.glb')) {
      setModelFailed(true)
      setModelName('Select a .glb export')
      return
    }
    setModelUrl(URL.createObjectURL(file))
    setModelName(file.name)
    setModelFailed(false)
    setSelectedPart(null)
    setExploded(false)
    setIsolated(false)
    setSpinning(!window.matchMedia('(prefers-reduced-motion: reduce)').matches)
    setPartCatalog([])
  }

  const useSchematic = () => {
    if (modelUrl?.startsWith('blob:')) URL.revokeObjectURL(modelUrl)
    setModelUrl(null)
    setModelName(null)
    setModelFailed(false)
    setSelectedPart(null)
    setExploded(false)
    setIsolated(false)
    setSpinning(false)
    setPartCatalog([])
  }

  const selectComponent = (componentId: string) => {
    setSelectedPart(null)
    onSelectComponent(componentId)
  }

  const resetCamera = () => setCameraKey((key) => key + 1)

  const toggleIsolation = () => {
    if (isolated) {
      setIsolated(false)
      setCameraKey((key) => key + 1)
    } else {
      setIsolated(true)
    }
  }

  const inspectPart = (part: PartInspection) => {
    setSelectedPart(part)
    preserveInspectedPartOnComponentChange.current = part.componentId !== selectedComponentId
    onSelectComponent(part.componentId)
  }

  return (
    <section className="viewer-panel panel">
      <div className="panel-heading viewer-heading">
        <div>
          <h2>GE 6B.03 · conceptual reference</h2>
        </div>
        <div className="viewer-actions">
          <span className={`model-state ${modelUrl && !modelFailed ? 'model-state-loaded' : ''}`}>
            <span className="state-dot" />
            {modelFailed ? 'SCHEMATIC FALLBACK' : modelUrl ? 'BLENDER GLB' : 'INTERACTIVE SCHEMATIC'}
          </span>
          <label className="button button-quiet file-button">
            <input type="file" accept=".glb,model/gltf-binary" onChange={onFileChange} />
            Load GLB
          </label>
          {modelUrl && <button type="button" className="button button-quiet" onClick={useSchematic}>Schematic</button>}
        </div>
      </div>
      <div className="viewer-stage">
        <Canvas
          dpr={[1, 1.5]}
          camera={{ position: [-6.4, -4.4, 7.6], fov: 35, near: 0.1, far: 100 }}
          gl={{ antialias: true, alpha: false }}
        >
          <color attach="background" args={['#0c141c']} />
          <ambientLight intensity={0.8} />
          <directionalLight position={[4, 8, 5]} intensity={2.1} color="#dce8ed" />
          <pointLight position={[-2.5, 1.2, 2.5]} intensity={9} distance={10} color="#a9c6c8" />
          <pointLight position={[1.4, 0.8, -2]} intensity={4} distance={8} color="#d5d9da" />
          <Suspense fallback={<SchematicTurbine components={components} selectedComponentId={selectedComponentId} onSelectComponent={selectComponent} />}>
            {modelUrl ? (
              <ModelBoundary
                key={modelUrl}
                onFailure={() => {
                  setModelFailed(true)
                  setPartCatalog([])
                }}
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
                />
              </ModelBoundary>
            ) : (
              <SchematicTurbine components={components} selectedComponentId={selectedComponentId} onSelectComponent={selectComponent} />
            )}
          </Suspense>
          <OrbitControls
            enableDamping
            dampingFactor={0.08}
            enablePan
            panSpeed={0.9}
            zoomSpeed={0.8}
            rotateSpeed={0.8}
            minDistance={0.45}
            maxDistance={26}
            minPolarAngle={0.035}
            maxPolarAngle={Math.PI - 0.035}
            makeDefault
          />
          <ViewerCameraReset resetKey={cameraKey} />
        </Canvas>
        <div className="viewer-axis-label axis-intake">Air inlet</div>
        <div className="viewer-axis-label axis-core">Core</div>
        <div className="viewer-axis-label axis-output">Generator</div>
        <div className="viewer-note">Orbit: drag · Pan: right-drag · Zoom: scroll · Click a part to inspect</div>
      </div>
      <div className="viewer-control-row" aria-label="3D model controls">
        <div className="viewer-control-group">
          <button type="button" className="button button-quiet" onClick={resetCamera}>Reset camera</button>
          <button type="button" className={`button button-quiet ${exploded ? 'is-active' : ''}`} aria-pressed={exploded} disabled={!modelInteractive} onClick={() => setExploded((value) => !value)}>
            {exploded ? 'Reassemble' : 'Explode view'}
          </button>
          <button type="button" className={`button button-quiet ${isolated ? 'is-active' : ''}`} aria-pressed={isolated} disabled={!modelInteractive} onClick={toggleIsolation}>
            {isolated ? 'Show all parts' : activeSelectedPart ? 'Isolate selected part' : 'Isolate component'}
          </button>
          <button type="button" className={`button button-quiet ${spinning ? 'is-active' : ''}`} aria-pressed={spinning} disabled={!modelInteractive} onClick={() => setSpinning((value) => !value)}>
            {spinning ? 'Pause rotor' : 'Spin rotor'}
          </button>
        </div>
        <span className="viewer-control-hint">
          {spinning
            ? <span className="rotor-status"><span className="rotor-status-dot" />Rotor motion on · visual only</span>
            : modelInteractive ? 'Choose a mesh below, then isolate it.' : 'Load the Blender GLB to use part controls.'}
        </span>
      </div>
      <div className="part-browser">
        <label htmlFor="model-part-select">Model sub-parts · {components.find((component) => component.component_id === selectedComponentId)?.label ?? selectedComponentId}</label>
        <select
          id="model-part-select"
          value={activeSelectedPart?.componentId === selectedComponentId ? activeSelectedPart.objectId : ''}
          disabled={!modelInteractive || !partCatalog.some((part) => part.componentId === selectedComponentId)}
          onChange={(event) => {
            const part = partCatalog.find((candidate) => candidate.objectId === event.target.value)
            if (part) inspectPart(part)
          }}
        >
          <option value="">Choose a mesh to inspect…</option>
          {partCatalog.filter((part) => part.componentId === selectedComponentId).map((part) => (
            <option key={part.objectId} value={part.objectId}>
              {part.name}{part.envelopeMm
                ? ` · ${part.envelopeMm} mm single casting`
                : part.referenceEnvelopeMm ? ` · ${part.referenceEnvelopeMm} mm stage reference` : ''}
            </option>
          ))}
        </select>
      </div>
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
              {activeSelectedPart.envelopeMm && <span>Single casting envelope: {activeSelectedPart.envelopeMm} mm</span>}
              {activeSelectedPart.massKg !== undefined && <span>Single casting listed mass: {activeSelectedPart.massKg} kg</span>}
              {activeSelectedPart.referenceLabel && <span>Related reference: {activeSelectedPart.referenceLabel}</span>}
              {activeSelectedPart.referenceEnvelopeMm && <span>Stage casting envelope: {activeSelectedPart.referenceEnvelopeMm} mm</span>}
              {activeSelectedPart.referenceMassKg !== undefined && <span>Stage casting listed mass: {activeSelectedPart.referenceMassKg} kg</span>}
              {activeSelectedPart.instanceIndex !== undefined && activeSelectedPart.instanceCount !== undefined && (
                <span>Visual instance {activeSelectedPart.instanceIndex} of {activeSelectedPart.instanceCount}</span>
              )}
            </div>
            {activeSelectedPart.instanceCountNote && <div className="part-inspection-note">{activeSelectedPart.instanceCountNote}</div>}
            {activeSelectedPart.dataNote && <div className="part-inspection-note">{activeSelectedPart.dataNote}</div>}
            {activeSelectedPart.geometryNote && <div className="part-inspection-note">{activeSelectedPart.geometryNote}</div>}
            {activeSelectedPart.source && <a className="part-inspection-source" href={activeSelectedPart.source} target="_blank" rel="noreferrer">Open public source ↗</a>}
          </>
        ) : (
          <div className="part-inspection-empty">
            {modelInteractive ? 'Click any visible mesh in the Blender model to inspect the sub-part and available public metadata.' : 'Sub-part inspection is available when the Blender GLB is loaded.'}
          </div>
        )}
        {spinning && <div className="visual-only-note">Rotor motion is illustrative only; it is not an RPM or operating-state prediction.</div>}
      </div>
      <div className="viewer-footnote">
        {modelName && !modelFailed ? `Loaded locally in this browser · ${modelName}` : 'No Blender export found in this workspace. The schematic is an interactive geometry scaffold.'}
      </div>
    </section>
  )
}
