import { describe, expect, it, vi } from 'vitest'
import { readThemePreference, writeThemePreference } from './router'

describe('theme persistence storage boundary', () => {
  it('uses system preference when reading storage is unavailable', () => {
    const storage = { getItem: vi.fn(() => { throw new Error('Storage unavailable') }) }
    expect(readThemePreference(storage)).toBe('system')
  })

  it('keeps the current session usable when writing storage is unavailable', () => {
    const storage = { setItem: vi.fn(() => { throw new Error('Storage unavailable') }) }
    expect(() => writeThemePreference(storage, 'dark')).not.toThrow()
    expect(storage.setItem).toHaveBeenCalledWith('turbineiq-theme', 'dark')
  })
})
