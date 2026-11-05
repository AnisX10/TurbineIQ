import { useContext, type ReactNode, type RefObject } from 'react'
import { Html } from '@react-three/drei'
import type { ThreeEvent } from '@react-three/fiber'
import type { SchematicTurbineSceneProps } from './types'
import { StageTokenContext } from './stageTokens'

interface PartProps {
  id: string
  position?: [number, number, number]
  outlineRadius?: number
  selected: boolean
  status: string
  onSelect: (componentId: string) => void
  children: ReactNode
  htmlPortal: SchematicTurbineSceneProps['htmlPortal']
}

function Part({ id, position, outlineRadius = 0.66, selected, status, onSelect, children, htmlPortal }: PartProps) {
  const stageTokens = useContext(StageTokenContext)
  const selectedTone = stageTokens.selected
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
      userData={{ turbineiqComponentId: id, turbineiqStatus: status }}
    >
      {children}
      <mesh rotation={[0, Math.PI / 2, 0]}>
        <torusGeometry args={[outlineRadius, selected ? 0.035 : 0.02, 8, 48]} />
        <meshStandardMaterial
          color={selected ? selectedTone : stageTokens.edge}
          metalness={0.62}
          roughness={0.43}
          transparent={status !== 'nominal' && !selected}
          opacity={status !== 'nominal' && !selected ? 0.78 : 1}
        />
      </mesh>
      {selected && <Html position={[0, outlineRadius + 0.42, 0]} center portal={htmlPortal as RefObject<HTMLElement>}>
        <span className="viewer-selection-label">{COMPONENT_LABELS[id] ?? id}</span>
      </Html>}
    </group>
  )
}

const COMPONENT_LABELS: Record<string, string> = {
  inlet: 'Air inlet',
  compressor: 'Compressor',
  combustor: 'Combustor',
  turbine: 'Turbine',
  shaft: 'Rotor shaft',
  generator: 'Generator',
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
  const stageTokens = useContext(StageTokenContext)
  return (
    <mesh position={[x, 0, 0]} rotation={[0, 0, Math.PI / 2]} castShadow receiveShadow>
      <cylinderGeometry args={[radius, radius, length, 48, 1, false]} />
      <meshStandardMaterial
        color={stageTokens.part || color}
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
  const stageTokens = useContext(StageTokenContext)
  return (
    <mesh position={[x, 0, 0]} rotation={[0, Math.PI / 2, 0]}>
      <torusGeometry args={[radius, 0.025, 10, 48]} />
      <meshStandardMaterial color={stageTokens.edge || color} metalness={0.78} roughness={0.3} />
    </mesh>
  )
}

function BladeRow({ x, count, radius, color }: { x: number; count: number; radius: number; color: string }) {
  const stageTokens = useContext(StageTokenContext)
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
            <meshStandardMaterial color={stageTokens.part || color} metalness={0.8} roughness={0.32} />
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

export function SchematicTurbine({
  components,
  selectedComponentId,
  onSelectComponent,
  htmlPortal,
}: SchematicTurbineSceneProps) {
  const statusById = new Map(components.map((component) => [component.component_id, component.status]))
  const selected = (id: string) => selectedComponentId === id
  const status = (id: string) => statusById.get(id) ?? 'nominal'

  return (
    <group position={[-0.15, 0.05, 0]}>
      <Part id="inlet" position={[-4.05, 0, 0]} outlineRadius={0.45} selected={selected('inlet')} status={status('inlet')} onSelect={onSelectComponent} htmlPortal={htmlPortal}>
        <AxialCylinder x={0} length={0.8} radius={0.43} color="#435660" />
        <Ring x={-0.33} radius={0.43} />
        <Ring x={0.33} radius={0.43} />
      </Part>
      <Part id="compressor" position={[-2.3, 0, 0]} outlineRadius={0.72} selected={selected('compressor')} status={status('compressor')} onSelect={onSelectComponent} htmlPortal={htmlPortal}>
        <AxialCylinder x={0} length={1.75} radius={0.7} color="#34444d" opacity={0.36} />
        {[-0.78, -0.39, 0, 0.39, 0.78].map((x) => <Ring key={x} x={x} radius={0.65} />)}
        {[-0.62, -0.22, 0.18, 0.58].map((x) => (
          <BladeRow key={x} x={x} count={10} radius={0.5} color="#8da0a6" />
        ))}
        <AxialCylinder x={0} length={1.6} radius={0.15} color="#9daeb4" />
      </Part>
      <Part id="combustor" position={[-0.25, 0, 0]} outlineRadius={0.56} selected={selected('combustor')} status={status('combustor')} onSelect={onSelectComponent} htmlPortal={htmlPortal}>
        <AxialCylinder x={0} length={1.15} radius={0.54} color="#765c44" opacity={0.7} />
        <AxialCylinder x={0} length={0.82} radius={0.34} color="#b97843" opacity={0.8} />
        {[-0.48, 0.48].map((x) => <Ring key={x} x={x} radius={0.52} color="#d49b61" />)}
      </Part>
      <Part id="turbine" position={[1.35, 0, 0]} outlineRadius={0.74} selected={selected('turbine')} status={status('turbine')} onSelect={onSelectComponent} htmlPortal={htmlPortal}>
        <AxialCylinder x={0} length={1.45} radius={0.72} color="#34444d" opacity={0.36} />
        {[-0.66, -0.22, 0.22, 0.66].map((x) => <Ring key={x} x={x} radius={0.68} />)}
        {[-0.45, 0, 0.45].map((x) => (
          <BladeRow key={x} x={x} count={12} radius={0.54} color="#9caeb3" />
        ))}
        <AxialCylinder x={0} length={1.3} radius={0.17} color="#9daeb4" />
      </Part>
      <Part id="shaft" position={[0.15, -0.02, 0]} outlineRadius={0.12} selected={selected('shaft')} status={status('shaft')} onSelect={onSelectComponent} htmlPortal={htmlPortal}>
        <AxialCylinder x={0} length={6.35} radius={0.095} color="#7d929a" />
      </Part>
      <Part id="generator" position={[4.12, 0, 0]} outlineRadius={0.6} selected={selected('generator')} status={status('generator')} onSelect={onSelectComponent} htmlPortal={htmlPortal}>
        <AxialCylinder x={0} length={1.4} radius={0.58} color="#465760" />
        {[-0.52, -0.27, 0, 0.27, 0.52].map((x) => <Ring key={x} x={x} radius={0.58} color="#8699a0" />)}
        <AxialCylinder x={0.82} length={0.3} radius={0.38} color="#3d4d55" />
      </Part>
      <gridHelper args={[12, 24, '#31414c', '#1d2a34']} position={[0, -1.08, 0]} />
    </group>
  )
}

