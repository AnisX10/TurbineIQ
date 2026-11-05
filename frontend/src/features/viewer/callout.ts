import { Box3, type Camera, Matrix4, Vector3 } from 'three'

export type CalloutPlacement = {
  position: [number, number, number]
  side: 'left' | 'right'
}

export function getCalloutPlacement(bounds: Box3, camera?: Camera, worldMatrix = new Matrix4()): CalloutPlacement | null {
  if (bounds.isEmpty()) return null

  const center = bounds.getCenter(new Vector3())
  const corners = [
    new Vector3(bounds.min.x, bounds.min.y, bounds.min.z),
    new Vector3(bounds.min.x, bounds.min.y, bounds.max.z),
    new Vector3(bounds.min.x, bounds.max.y, bounds.min.z),
    new Vector3(bounds.min.x, bounds.max.y, bounds.max.z),
    new Vector3(bounds.max.x, bounds.min.y, bounds.min.z),
    new Vector3(bounds.max.x, bounds.min.y, bounds.max.z),
    new Vector3(bounds.max.x, bounds.max.y, bounds.min.z),
    new Vector3(bounds.max.x, bounds.max.y, bounds.max.z),
  ]

  if (!camera) return { position: [bounds.max.x, bounds.max.y, center.z], side: 'right' }

  camera.updateMatrixWorld()
  const projected = corners.map((point) => ({ point, screen: point.clone().applyMatrix4(worldMatrix).project(camera) }))
  const centerX = center.clone().applyMatrix4(worldMatrix).project(camera).x
  const minimumX = Math.min(...projected.map(({ screen }) => screen.x))
  const maximumX = Math.max(...projected.map(({ screen }) => screen.x))
  let side: CalloutPlacement['side'] = centerX < 0 ? 'left' : 'right'
  if (side === 'left' && minimumX < -0.8) side = 'right'
  if (side === 'right' && maximumX > 0.8) side = 'left'

  const targetX = side === 'left' ? minimumX : maximumX
  const edge = projected
    .filter(({ screen }) => Math.abs(screen.x - targetX) < 1e-6)
    .sort((left, right) => right.screen.y - left.screen.y)[0]

  return { position: edge.point.toArray(), side }
}
