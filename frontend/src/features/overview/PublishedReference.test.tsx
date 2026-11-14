import { describe, expect, it } from 'vitest'
import { PUBLISHED_6B03_REFERENCE } from '../../lib/publishedReference'

describe('published 6B.03 reference wording', () => {
  it('states that the cycle model is uncalibrated and does not claim calibration', () => {
    expect(PUBLISHED_6B03_REFERENCE.caveat).toMatch(/uncalibrated/)
    expect(PUBLISHED_6B03_REFERENCE.caveat).not.toMatch(/is calibrated/)
  })
})
