import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AppErrorBoundary } from './AppErrorBoundary'

function BrokenScreen(): ReactElement {
  throw new Error('private implementation detail')
}

describe('AppErrorBoundary', () => {
  afterEach(() => vi.restoreAllMocks())

  it('shows a calm reload fallback without exposing the exception', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    render(<AppErrorBoundary><BrokenScreen /></AppErrorBoundary>)

    const fallback = screen.getByRole('alert')
    expect(fallback.textContent).toContain('TurbineIQ could not display this screen')
    expect(fallback.textContent).not.toContain('private implementation detail')
    expect(screen.getByRole('button', { name: 'Reload workspace' })).toBeDefined()
  })
})
