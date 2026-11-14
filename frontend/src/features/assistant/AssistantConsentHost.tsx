import { useEffect, useState } from 'react'
import { api } from '../../api'
import type { AssistantProviderStatus } from '../../api'
import { useTurbineStore } from '../../app/useTurbineStore'
import { Sheet } from '../../components/ui/Sheet'

export default function AssistantConsentHost() {
  const { state, dispatch } = useTurbineStore()
  const [providerStatus, setProviderStatus] = useState<AssistantProviderStatus | null>(null)
  const [grantError, setGrantError] = useState('')
  const [granting, setGranting] = useState(false)
  useEffect(() => {
    if (!state.assistantConsentOpen) return
    let active = true
    void api.assistantStatus().then((status) => { if (active) setProviderStatus(status) }).catch(() => { if (active) setProviderStatus(null) })
    return () => { active = false }
  }, [state.assistantConsentOpen])

  const close = () => {
    setGrantError('')
    dispatch({ type: 'assistant-consent-open', value: { open: false, resumeDock: false } })
  }
  const accept = async () => {
    setGranting(true)
    setGrantError('')
    try {
      const grant = await api.grantConsent(state.assistantIncludeDocuments)
      dispatch({ type: 'assistant-consent-token', value: grant.consent_token })
      dispatch({ type: 'assistant-consent-accepted', value: true })
      dispatch({ type: 'assistant-consent-open', value: { open: false, resumeDock: false } })
    } catch (error) {
      setGrantError(error instanceof Error ? error.message : 'The local server did not record your consent. Retry.')
    } finally {
      setGranting(false)
    }
  }
  const provider = providerStatus
    ? `${providerStatus.configured ? 'Configured provider' : 'Provider not configured'}: ${providerStatus.provider} · ${providerStatus.base_url_host} · ${providerStatus.model}`
    : 'Provider configuration unavailable'

  return <Sheet open={state.assistantConsentOpen} onClose={close} className="sheet-consent assistant-consent-sheet" labelledBy="cloud-consent-title" describedBy="cloud-consent-copy">
    <h2 id="cloud-consent-title">Review Cloud sharing</h2>
    <p>{provider}</p>
    <p id="cloud-consent-copy">The named provider receives your question, TurbineIQ assistant instructions and allowed-tool descriptions, server-recomputed synthetic run metadata, selected sample and component when present, and results from local tools used to answer. Matching document excerpts and citations are sent only when you enable the separate option below and the assistant searches local documents. Free provider plans may log or retain prompts under their own policies. The API key stays in the local server and is not sent to the browser.</p>
    <label className="assistant-consent-check"><input type="checkbox" checked={state.assistantIncludeDocuments} onChange={(event) => dispatch({ type: 'assistant-documents', value: event.target.checked })} /><span className="assistant-consent-checkbox-mark" aria-hidden="true" />Allow local document excerpts and citations to be sent if the assistant searches local documents.</label>
    <p className="assistant-consent-note">This option is off by default. Your Cloud choice is remembered only for this browser session. The server records your choice, ties it to this provider, and refuses Cloud requests without it.</p>
    {grantError && <p className="assistant-consent-note" role="alert">{grantError}</p>}
    <div className="assistant-consent-actions"><button type="button" className="button-quiet" onClick={close}>Cancel</button><button type="button" className="assistant-ask-button" data-sheet-autofocus disabled={granting} onClick={() => void accept()}>Continue to Cloud</button></div>
  </Sheet>
}
