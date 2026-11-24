import { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { Html, OrbitControls, useGLTF } from '@react-three/drei'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Box3, Color, Group, Mesh, MeshStandardMaterial, Vector3 } from 'three'
import type { Object3D, PointLight } from 'three'
import { ModelBoundary } from '../viewer/ModelBoundary'
import { StageLights } from '../viewer/lights'
import { useStageTokens } from '../viewer/stageTokens'
import { componentIdFor, isRotorPart, normalizedObjectName } from '../viewer/selection'
import type { Callout } from './twinLogic'
import { heatFraction, rotorRadPerSecond } from './twinLogic'

const MODEL_PATH = '/models/turbine.glb'
/** Callouts pinned under the model, so the four do not crowd one another above it. */
const BELOW = new Set<Callout['id']>(['combustor', 'exhaust'])
const HOT_GLOW = new Color('#ff6a1f')
const OVER_LIMIT_GLOW = new Color('#ff1e12')
const FLAME_GLOW = new Color('#ffad42')
const BLACK = new Color('#000000')

export interface LiveTurbineProps {
  speedPu: number
  flame: boolean
  tripped: boolean
  exhaustK: number
  limitK: number
  callouts: Callout[]
  reduceMotion: boolean
}

type Role = 'rotor' | 'flame' | 'hot' | 'plain'

interface Prepared {
  root: Group
  meshes: Array<{ mesh: Mesh; role: Role; material: MeshStandardMaterial }>
  rotor: Object3D[]
  anchors: Record<Callout['id'], [number, number, number]>
  flameAt: [number, number, number]
}

function roleOf(mesh: Mesh, componentId: string | null): Role {
  const name = normalizedObjectName(mesh.name)
  if (name.startsWith('combustion liner') || name.startsWith('transition piece')) return 'flame'
  if (componentId === 'turbine' || name.includes('exhaust') || name.startsWith('stage ')) return 'hot'
  return 'plain'
}

function prepare(source: Object3D): Prepared {
  const scene = source.clone(true)
  const wrapper = new Group()
  wrapper.add(scene)
  const bounds = new Box3().setFromObject(wrapper)
  const size = bounds.getSize(new Vector3())
  scene.position.sub(bounds.getCenter(new Vector3()))
  wrapper.scale.setScalar(8.6 / Math.max(size.x, size.y, size.z, 0.001))
  wrapper.updateMatrixWorld(true)

  const meshes: Prepared['meshes'] = []
  const rotor: Object3D[] = []
  const boxes: Record<string, Box3> = {}
  const grow = (key: string, object: Object3D) => {
    boxes[key] = (boxes[key] ?? new Box3()).expandByObject(object)
  }
  scene.traverse((object) => {
    if (isRotorPart(object)) rotor.push(object)
    if (!(object instanceof Mesh)) return
    const componentId = componentIdFor(object)
    const base = Array.isArray(object.material) ? object.material[0] : object.material
    const material = base instanceof MeshStandardMaterial ? base.clone() : new MeshStandardMaterial()
    object.material = material
    meshes.push({ mesh: object, role: roleOf(object, componentId), material })
    if (componentId) grow(componentId, object)
    if (normalizedObjectName(object.name).includes('exhaust')) grow('exhaust', object)
  })
  const top = (key: string, fallback: string, below = false): [number, number, number] => {
    const box = boxes[key] ?? boxes[fallback] ?? bounds
    const center = box.getCenter(new Vector3())
    return [center.x, below ? box.min.y : box.max.y, center.z]
  }
  const combustor = (boxes.combustor ?? bounds).getCenter(new Vector3())
  return {
    root: wrapper,
    meshes,
    rotor,
    anchors: {
      compressor: top('compressor', 'inlet'),
      combustor: top('combustor', 'turbine', true),
      turbine: top('turbine', 'combustor'),
      exhaust: top('exhaust', 'turbine', true),
    },
    flameAt: [combustor.x, combustor.y, combustor.z],
  }
}

/** Colour the model: neutral grey, flame glow in the cans, heat glow in the hot section. */
function paint(prepared: Prepared, partColor: string, flame: boolean, tripped: boolean, exhaustK: number, limitK: number, light: PointLight | null) {
  const heat = tripped ? 0 : heatFraction(exhaustK, limitK)
  const over = heat > 1
  const part = new Color(partColor)
  for (const { role, material } of prepared.meshes) {
    material.color.copy(part)
    if (role === 'flame' && flame && !tripped) {
      material.emissive.copy(FLAME_GLOW)
      material.emissiveIntensity = 0.55 + 0.35 * Math.min(1, heat)
    } else if ((role === 'hot' || role === 'flame') && heat > 0.05) {
      material.emissive.copy(over ? OVER_LIMIT_GLOW : HOT_GLOW)
      material.emissiveIntensity = over ? 0.75 : 0.2 * Math.min(1, heat) ** 2
    } else {
      material.emissive.copy(BLACK)
      material.emissiveIntensity = 0
    }
    material.needsUpdate = true
  }
  if (light) light.intensity = flame && !tripped ? 6 + 8 * Math.min(1, heat) : 0
}

/** Turn the rotor parts; returns whether anything moved. */
function spin(rotor: Object3D[], radPerSecond: number, delta: number): boolean {
  if (radPerSecond <= 0) return false
  const step = Math.min(delta, 0.05) * radPerSecond
  for (const object of rotor) object.rotation.x += step
  return true
}

function LiveModel({ speedPu, flame, tripped, exhaustK, limitK, callouts, reduceMotion }: LiveTurbineProps) {
  const gltf = useGLTF(MODEL_PATH, false, true)
  const tokens = useStageTokens()
  const invalidate = useThree((s) => s.invalidate)
  const prepared = useMemo(() => prepare(gltf.scene), [gltf.scene])
  const light = useRef<PointLight>(null)
  const rad = rotorRadPerSecond(speedPu, reduceMotion)
  const radRef = useRef(rad)
  useEffect(() => { radRef.current = rad; invalidate() }, [rad, invalidate])

  useEffect(() => {
    paint(prepared, tokens.part, flame, tripped, exhaustK, limitK, light.current)
    invalidate()
  }, [prepared, tokens.part, flame, tripped, exhaustK, limitK, invalidate])

  useFrame((state, delta) => {
    if (spin(prepared.rotor, radRef.current, delta)) state.invalidate()
  })

  return (
    <>
      <primitive object={prepared.root} />
      <pointLight ref={light} position={prepared.flameAt} distance={6} decay={1.6} color="#ffb259" intensity={0} />
      {callouts.map((callout) => (
        <Html key={callout.id} position={prepared.anchors[callout.id]} zIndexRange={[20, 0]} style={{ pointerEvents: 'none' }}>
          <div className={`twin-callout twin-callout--${callout.id} is-${callout.tone} ${BELOW.has(callout.id) ? 'is-below' : ''}`} data-testid={`callout-${callout.id}`}>
            <span className="twin-callout-label">{callout.label}</span>
            <strong className="twin-callout-value">{callout.value}</strong>
          </div>
        </Html>
      ))}
    </>
  )
}

const CAMERA_HOME = new Vector3(-5.2, 3.4, 8.4)

/** Step the camera back on narrow stages (a phone) so the whole unit stays in view. */
function FitCamera() {
  const camera = useThree((s) => s.camera)
  const width = useThree((s) => s.size.width)
  const height = useThree((s) => s.size.height)
  const invalidate = useThree((s) => s.invalidate)
  useEffect(() => {
    const aspect = width / Math.max(1, height)
    const scale = aspect < 1.7 ? Math.min(1.9, 1.7 / aspect) : 1
    camera.position.copy(CAMERA_HOME).multiplyScalar(scale)
    camera.lookAt(0, 0, 0)
    invalidate()
  }, [camera, width, height, invalidate])
  return null
}

function Invalidate({ deps }: { deps: unknown[] }) {
  const invalidate = useThree((s) => s.invalidate)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { invalidate() }, deps)
  return null
}

/** The 3D turbine driven by the live simulation (rotor speed, flame, hot-section heat). */
export function LiveTurbine(props: LiveTurbineProps) {
  const tokens = useStageTokens()
  const [failed, setFailed] = useState(false)
  const summary = `${props.tripped ? 'Tripped. ' : ''}Rotor at ${(props.speedPu * 100).toFixed(0)} % speed, ${props.flame ? 'flame on' : 'no flame'}, exhaust ${(props.exhaustK - 273.15).toFixed(0)} °C.`
  return (
    <div className="twin-stage-canvas">
      <Canvas
        frameloop="demand"
        dpr={[1, 2]}
        camera={{ position: [-5.2, 3.4, 8.4], fov: 32, near: 0.1, far: 100 }}
        gl={{ antialias: true, alpha: false, preserveDrawingBuffer: true }}
        role="img"
        aria-label={`Live 3D model of the simulated gas turbine. ${summary} Drag to orbit.`}
      >
        <color attach="background" args={[tokens.background]} />
        <StageLights tokens={tokens} />
        <Invalidate deps={[tokens, props.callouts, props.flame, props.tripped, props.exhaustK]} />
        <ModelBoundary onFailure={() => setFailed(true)} fallback={null}>
          <Suspense fallback={null}>
            <LiveModel {...props} />
          </Suspense>
        </ModelBoundary>
        <FitCamera />
        <OrbitControls enablePan={false} enableDamping={!props.reduceMotion} dampingFactor={0.08} minDistance={4} maxDistance={22} makeDefault />
      </Canvas>
      {failed && <p className="twin-stage-fallback" role="status">The 3D model could not be loaded. The values beside it are live.</p>}
    </div>
  )
}
