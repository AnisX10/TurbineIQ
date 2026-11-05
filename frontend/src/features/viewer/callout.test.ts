import { describe, expect, it } from 'vitest'
import { Box3, Vector3 } from 'three'
import { getCalloutAnchor } from './callout'

describe('getCalloutAnchor', () => {
  it('anchors at the upper outer edge of a mesh bounding box', () => {
    const bounds = new Box3(new Vector3(-2, -1, -3), new Vector3(4, 5, 3))

    expect(getCalloutAnchor(bounds)).toEqual([4, 5, 0])
  })

  it('returns no anchor for an empty bounding box', () => {
    expect(getCalloutAnchor(new Box3())).toBeNull()
  })
})
