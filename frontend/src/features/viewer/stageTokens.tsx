import { createContext, useEffect, useState } from 'react'

function readCssColor(token: string, fallback: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(token).trim() || fallback
}

export interface StageTokens {
  background: string
  part: string
  edge: string
  selected: string
  ambient: number
  keyLight: number
  fillLight: number
  rimLight: number
}

const DEFAULT_STAGE_TOKENS: StageTokens = { background: '#ffffff', part: '#d9dde3', edge: '#8a8f98', selected: '#1d5fbf', ambient: 0.8, keyLight: 2.1, fillLight: 9, rimLight: 4 }
export const StageTokenContext = createContext<StageTokens>(DEFAULT_STAGE_TOKENS)

function readStageTokens(): StageTokens {
  const root = document.documentElement
  const dark = root.dataset.theme === 'dark' || (!root.dataset.theme && window.matchMedia('(prefers-color-scheme: dark)').matches)
  return {
    background: readCssColor('--stage-bg', DEFAULT_STAGE_TOKENS.background),
    part: readCssColor('--stage-part', DEFAULT_STAGE_TOKENS.part),
    edge: readCssColor('--stage-edge', DEFAULT_STAGE_TOKENS.edge),
    selected: readCssColor('--stage-selected', DEFAULT_STAGE_TOKENS.selected),
    ambient: dark ? 4 : DEFAULT_STAGE_TOKENS.ambient,
    keyLight: dark ? 7 : DEFAULT_STAGE_TOKENS.keyLight,
    fillLight: dark ? 32 : DEFAULT_STAGE_TOKENS.fillLight,
    rimLight: dark ? 24 : DEFAULT_STAGE_TOKENS.rimLight,
  }
}

export function useStageTokens(): StageTokens {
  const [tokens, setTokens] = useState(readStageTokens)
  useEffect(() => {
    const root = document.documentElement
    const refresh = () => setTokens(readStageTokens())
    const observer = new MutationObserver(refresh)
    observer.observe(root, { attributes: true, attributeFilter: ['data-theme'] })
    const preference = window.matchMedia('(prefers-color-scheme: dark)')
    preference.addEventListener('change', refresh)
    refresh()
    return () => {
      observer.disconnect()
      preference.removeEventListener('change', refresh)
    }
  }, [])
  return tokens
}

