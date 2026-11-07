import { useState } from 'react'
import { Check, Copy } from 'lucide-react'
import { ENGINE_ACTIVATION_COMMANDS, ENGINE_START_COMMAND } from '../../lib/engine'
import './EngineOfflineBanner.css'

export function EngineOfflineBanner() {
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'unavailable'>('idle')

  const copyCommand = async () => {
    try {
      await navigator.clipboard.writeText(ENGINE_START_COMMAND)
      setCopyState('copied')
    } catch {
      setCopyState('unavailable')
    }
  }

  return (
    <div className="engine-banner" role="alert">
      <strong>Local engine offline.</strong>
      <span>From the project root, activate the virtual environment for your shell:</span>
      <div className="engine-activation-list">
        <span>PowerShell</span><code>{ENGINE_ACTIVATION_COMMANDS.powershell}</code>
        <span>POSIX shell</span><code>{ENGINE_ACTIVATION_COMMANDS.posix}</code>
      </div>
      <div className="engine-start-row">
        <code>{ENGINE_START_COMMAND}</code>
        <button className="engine-copy" type="button" onClick={() => void copyCommand()} aria-label="Copy API start command">
          {copyState === 'copied' ? <Check size={15} aria-hidden="true" /> : <Copy size={15} aria-hidden="true" />}
          <span>{copyState === 'copied' ? 'Copied' : 'Copy command'}</span>
        </button>
      </div>
      <span className="engine-copy-status" aria-live="polite">{copyState === 'unavailable' ? 'Clipboard access is unavailable in this browser.' : ''}</span>
    </div>
  )
}
