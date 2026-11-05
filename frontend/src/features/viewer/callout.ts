import { Box3, Vector3 } from 'three'

export function getCalloutAnchor(bounds: Box3): [number, number, number] | null {
  if (bounds.isEmpty()) return null

  const center = bounds.getCenter(new Vector3())
  return [bounds.max.x, bounds.max.y, center.z]
}
