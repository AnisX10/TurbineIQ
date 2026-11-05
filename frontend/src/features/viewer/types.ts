import type { TwinComponentState } from '../../types'
import type { Vector3 } from 'three'

export interface SchematicTurbineProps {
  components: TwinComponentState[]
  selectedComponentId: string
  onSelectComponent: (componentId: string) => void
}

export interface TurbineViewerProps extends SchematicTurbineProps {
  view: 'glb' | 'schematic'
  exploded: boolean
  isolated: boolean
  spinning: boolean
  cameraKey: number
  onModelStatus: (status: { available: boolean; failed: boolean }) => void
}

export interface PartInspection {
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

export const EXPLODED_OFFSETS: Record<string, [number, number, number]> = {
  inlet: [-0.7, 0, 0],
  compressor: [-0.1, 0.18, 0.22],
  combustor: [0, 0.82, 0.66],
  turbine: [0.35, -0.12, 0.26],
  shaft: [0, -0.78, -0.54],
  generator: [0.92, 0, 0],
}

export interface ViewerControls {
  target: Vector3
  update: () => void
}

export interface CameraFocusTarget {
  position: [number, number, number]
  target: [number, number, number]
}
