import { type BufferGeometry, type Camera, Matrix4, Vector3 } from 'three'

export const CALLOUT_GAP_PX = 40

export type CalloutPlacement = {
  position: [number, number, number]
  side: 'left' | 'right'
  gap: number
  maxWidth: number
}

export function getGeometryCentroid(geometry: BufferGeometry): Vector3 | null {
  const position = geometry.getAttribute('position')
  if (!position || position.count === 0) return null

  const centroid = new Vector3()
  for (let index = 0; index < position.count; index += 1) {
    centroid.x += position.getX(index)
    centroid.y += position.getY(index)
    centroid.z += position.getZ(index)
  }
  return centroid.multiplyScalar(1 / position.count)
}

export function getCalloutPlacement(
  centroid: Vector3,
  camera: Camera,
  worldMatrix: Matrix4,
  modelCenter: Vector3,
  viewportWidth: number,
  label: string,
): CalloutPlacement | null {
  camera.updateMatrixWorld()
  const anchorNdc = centroid.clone().applyMatrix4(worldMatrix).project(camera)
  const modelCenterNdc = modelCenter.clone().project(camera)
  const outward: CalloutPlacement['side'] = anchorNdc.x < modelCenterNdc.x ? 'left' : 'right'
  const anchorX = (anchorNdc.x + 1) * viewportWidth / 2
  const desiredWidth = Math.min(190, Math.max(64, label.length * 7.2 + 8))
  const margin = 8
  const available = (side: CalloutPlacement['side']) => side === 'left' ? anchorX - margin : viewportWidth - anchorX - margin
  const longestWordWidth = Math.max(40, ...label.split(/\s+/).map((word) => word.length * 7.2 + 4))
  const minimumSpace = CALLOUT_GAP_PX + Math.min(desiredWidth, longestWordWidth)
  let side = outward
  if (available(side) < minimumSpace && available(side === 'left' ? 'right' : 'left') > available(side)) {
    side = side === 'left' ? 'right' : 'left'
  }
  const maxWidth = Math.max(40, Math.min(desiredWidth, available(side) - CALLOUT_GAP_PX))

  return {
    position: centroid.toArray(),
    side,
    gap: CALLOUT_GAP_PX,
    maxWidth,
  }
}
