import type { RefObject } from 'react'
import { useTurbineStore } from '../../app/useTurbineStore'
import { Sheet } from '../../components/ui/Sheet'
import { AssistantWorkspace } from './AssistantWorkspace'

export default function AssistantDock({ askButtonRef }: { askButtonRef: RefObject<HTMLButtonElement | null> }) {
  const { state, dispatch } = useTurbineStore()
  return <Sheet
    open={state.assistantOpen && !state.assistantConsentOpen}
    onClose={() => dispatch({ type: 'assistant-open', value: false })}
    className="assistant-dock-sheet"
    labelledBy="assistant-dock-title"
    returnFocusTo={askButtonRef}
  >
    <AssistantWorkspace variant="dock" onClose={() => dispatch({ type: 'assistant-open', value: false })} />
  </Sheet>
}
