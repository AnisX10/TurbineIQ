import { describe, expect, it } from 'vitest'
import { BufferGeometry, Float32BufferAttribute, Matrix4, PerspectiveCamera, Vector3 } from 'three'
import { CALLOUT_GAP_PX, getCalloutPlacement, getGeometryCentroid } from './callout'

function geometryFromPoints(points: number[]) {
  const geometry = new BufferGeometry()
  geometry.setAttribute('position', new Float32BufferAttribute(points, 3))
  return geometry
}

function cameraAtOrigin() {
  const camera = new PerspectiveCamera(45, 1, 0.1, 100)
  camera.position.set(0, 0, 12)
  camera.lookAt(0, 0, 0)
  return camera
}

describe('getGeometryCentroid', () => {
  it('uses the centroid of the visible mesh vertices rather than a bounding-box corner', () => {
    const geometry = geometryFromPoints([
      -1, -1, 0,
      3, -1, 0,
      3, 1, 0,
      -1, 1, 0,
    ])

    expect(getGeometryCentroid(geometry)?.toArray()).toEqual([1, 0, 0])
  })

  it('returns null when the mesh has no visible vertices', () => {
    expect(getGeometryCentroid(new BufferGeometry())).toBeNull()
  })
})

describe('getCalloutPlacement', () => {
  it('anchors at the projected centroid and offsets the label by a visible leader line', () => {
    const camera = cameraAtOrigin()
    const centroid = new Vector3(-1, 0, 0)
    const placement = getCalloutPlacement(centroid, camera, new Matrix4(), new Vector3(), 1440, 'Compressor')

    expect(placement).toMatchObject({ position: [-1, 0, 0], side: 'left', gap: 40 })
    expect(placement?.maxWidth).toBeGreaterThan(0)
  })

  it('keeps a wide, long part label outward from the model center with the full leader gap', () => {
    const camera = cameraAtOrigin()
    const wideLongPart = geometryFromPoints([
      -5, -0.5, 0, 5, -0.5, 0,
      5, 0.5, 0, -5, 0.5, 0,
    ])
    const centroid = getGeometryCentroid(wideLongPart)
    const meshWorld = new Matrix4().makeTranslation(-2, 0, 0)
    const placement = centroid && getCalloutPlacement(
      centroid,
      camera,
      meshWorld,
      new Vector3(),
      1440,
      'Compressor casing wide section',
    )

    expect(centroid?.toArray()).toEqual([0, 0, 0])
    expect(placement).toMatchObject({ position: [0, 0, 0], side: 'left', gap: CALLOUT_GAP_PX })
    const projectedAnchor = new Vector3(0, 0, 0).applyMatrix4(meshWorld).project(camera)
    const anchorX = (projectedAnchor.x + 1) * 1440 / 2
    expect(CALLOUT_GAP_PX + (placement?.maxWidth ?? 0) + 8).toBeLessThanOrEqual(anchorX)
    expect(placement?.maxWidth).toBeGreaterThan(100)
  })

  it('switches sides only when the outward side cannot fit the minimum readable label', () => {
    const camera = cameraAtOrigin()
    const placement = getCalloutPlacement(
      new Vector3(-4.8, 0, 0),
      camera,
      new Matrix4(),
      new Vector3(),
      320,
      'Compressor',
    )

    expect(placement?.side).toBe('right')
  })
})
