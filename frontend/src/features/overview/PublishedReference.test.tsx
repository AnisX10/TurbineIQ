import { describe, expect, it } from 'vitest'
import { PUBLISHED_6B03_REFERENCE } from '../../lib/publishedReference'

describe('published 6B.03 reference wording', () => {
  it('says the fit agrees by construction and does not claim independent validation', () => {
    expect(PUBLISHED_6B03_REFERENCE.caveat).toMatch(/by construction/)
    expect(PUBLISHED_6B03_REFERENCE.caveat).toMatch(/not independent validation/)
    expect(PUBLISHED_6B03_REFERENCE.caveat).not.toMatch(/uncalibrated/)
  })
})
