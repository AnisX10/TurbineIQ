import { describe, expect, it } from 'vitest'
import { Box3, Matrix4, PerspectiveCamera, Vector3 } from 'three'
import { getCalloutPlacement } from './callout'

describe('getCalloutPlacement', () => {
  it('anchors at the upper outer edge of a mesh bounding box', () => {
    const bounds = new Box3(new Vector3(-2, -1, -3), new Vector3(4, 5, 3))

    expect(getCalloutPlacement(bounds)).toEqual({ position: [4, 5, 0], side: 'right' })
  })

  it('projects a transformed mesh while keeping the anchor in mesh-local coordinates', () => {
    const camera = new PerspectiveCamera(45, 1, 0.1, 100)
    camera.position.set(10, 0, 10)
    camera.lookAt(10, 0, 0)
    const bounds = new Box3(new Vector3(-1.5, -1, -1), new Vector3(-0.5, 1, 1))
    const worldMatrix = new Matrix4().makeTranslation(10, 0, 0)

    expect(getCalloutPlacement(bounds, camera, worldMatrix)).toMatchObject({ position: [-1.5, 1, 1], side: 'left' })
  })

  it('puts the callout outside the component edge and points it away from the model center', () => {
    const camera = new PerspectiveCamera(45, 1, 0.1, 100)
    camera.position.set(0, 0, 10)
    camera.lookAt(0, 0, 0)
    const left = new Box3(new Vector3(-1.5, -1, -1), new Vector3(-0.5, 1, 1))
    const right = new Box3(new Vector3(0.5, -1, -1), new Vector3(1.5, 1, 1))

    expect(getCalloutPlacement(left, camera)).toMatchObject({ position: [-1.5, 1, 1], side: 'left' })
    expect(getCalloutPlacement(right, camera)).toMatchObject({ position: [1.5, 1, 1], side: 'right' })
  })

  it('returns no anchor for an empty bounding box', () => {
    expect(getCalloutPlacement(new Box3())).toBeNull()
  })
})
