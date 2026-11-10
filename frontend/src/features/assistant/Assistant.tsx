import { useCallback, useMemo, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent as ReactKeyboardEvent } from 'react'
import { api } from '../../api'
import { useTurbineStore } from '../../app/useTurbineStore'
import type { AssistantResponse, SelectedTwinSelection } from '../../types'
import { EngineOfflineBanner } from '../../components/ui/EngineOfflineBanner'
import { Sheet } from '../../components/ui/Sheet'
import './Assistant.css'

interface ConversationItem {
  id: number
  question: string
  answer?: AssistantResponse
  error?: string
}

function ConsentSheet({ open, onCancel, onConfirm, includeDocuments, onIncludeDocuments }: { open: boolean; onCancel: () => void; onConfirm: () => void; includeDocuments: boolean; onIncludeDocuments: (value: boolean) => void }) {
  return <Sheet open={open} onClose={onCancel} className="sheet-consent assistant-consent-sheet" labelledBy="cloud-consent-title" describedBy="cloud-consent-copy">
    <h2 id="cloud-consent-title">Review Cloud sharing</h2>
    <p id="cloud-consent-copy">The configured provider receives your question, TurbineIQ assistant instructions and allowed-tool descriptions, and the server-recomputed synthetic run metadata, selected sample, and selected component when present. It also receives results from local tools used to answer. If you enable the option below and the assistant searches local documents, the matching excerpts and citations are sent too.</p>
    <label className="assistant-consent-check"><input type="checkbox" checked={includeDocuments} onChange={(event) => onIncludeDocuments(event.target.checked)} /><span className="assistant-consent-checkbox-mark" aria-hidden="true" />Allow local document excerpts and citations to be sent if the assistant searches local documents.</label>
    <p className="assistant-consent-note">This option is off by default. The server still enforces document consent.</p>
    <div className="assistant-consent-actions"><button type="button" className="button-quiet" onClick={onCancel}>Cancel</button><button type="button" className="assistant-ask-button" data-sheet-autofocus onClick={onConfirm}>Continue to Cloud</button></div>
  </Sheet>
}

export default function Assistant() {
  const { state } = useTurbineStore()
  const [cloud, setCloud] = useState(false)
  const [consentOpen, setConsentOpen] = useState(false)
  const [includeDocuments, setIncludeDocuments] = useState(false)
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState<ConversationItem[]>([])
  const [busy, setBusy] = useState(false)
  const nextId = useRef(1)
  const composer = useRef<HTMLTextAreaElement>(null)
  const snapshot = state.run?.snapshots[state.sampleIndex] ?? null
  const selectedComponentId = state.componentId ?? 'compressor'
  const component = snapshot?.components.find((item) => item.component_id === selectedComponentId)
  const scenarioName = snapshot?.scenario_name ?? state.run?.run.scenario_name ?? state.scenarios.find((item) => item.scenario_id === state.scenarioId)?.name ?? state.scenarioId
  const selectedTwin: SelectedTwinSelection | null = useMemo(() => snapshot && component ? {
    scenario_id: snapshot.scenario_id,
    seed: snapshot.seed,
    sample_index: snapshot.sample_index,
    selected_component_id: component.component_id,
  } : null, [snapshot, component])
  const suggestions = [
    'Explain the selected sample residual.',
    'Which assumption sets the compressor efficiency reference?',
    'What evidence supports the simplified Brayton-cycle assumptions?',
  ]

  const cancelConsent = useCallback(() => { setConsentOpen(false); setCloud(false) }, [])
  const confirmConsent = useCallback(() => { setConsentOpen(false); setCloud(true) }, [])
  const selectCloud = () => {
    if (cloud) return
    setConsentOpen(true)
  }
  const runQuestion = async (text: string, id: number) => {
    setBusy(true)
    try {
      const answer = await api.ask(text, cloud, cloud && includeDocuments, selectedTwin)
      setMessages((items) => items.map((item) => item.id === id ? { ...item, answer } : item))
    } catch (error) {
      const message = error instanceof Error ? error.message : 'The assistant request failed. Retry the question.'
      setMessages((items) => items.map((item) => item.id === id ? { ...item, error: message } : item))
    } finally {
      setBusy(false)
      composer.current?.focus()
    }
  }
  const ask = async (event?: FormEvent) => {
    event?.preventDefault()
    const text = question.trim()
    if (!text || busy) return
    const id = nextId.current++
    setMessages((items) => [...items, { id, question: text }])
    setQuestion('')
    if (composer.current) composer.current.style.height = '36px'
    await runQuestion(text, id)
  }
  const retryQuestion = (item: ConversationItem) => {
    if (busy) return
    setMessages((items) => items.map((message) => message.id === item.id ? { ...message, error: undefined, answer: undefined } : message))
    void runQuestion(item.question, item.id)
  }
  const onComposerKeyDown = (event: ReactKeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void ask() }
  }

  return (
    <div className="assistant-page" id="route-outlet">
      <section className="assistant-workspace" aria-label="Engineering assistant">
        <div className="assistant-mode-row"><div><h2>Ask about the current sample</h2></div>
          <div className="assistant-mode-segmented" role="group" aria-label="Assistant deployment mode"><button type="button" aria-pressed={!cloud} onClick={() => setCloud(false)}>Local <span>demo-safe</span></button><button type="button" aria-pressed={cloud} onClick={selectCloud}>Cloud</button></div>
        </div>
        <div className="assistant-context" aria-label="Current server-recomputed context"><span>{scenarioName}</span><span>Seed {snapshot?.seed ?? state.seed}</span><span>Sample {snapshot ? snapshot.sample_index + 1 : state.sampleIndex + 1}</span><span>{component?.label ?? selectedComponentId}</span></div>
        {state.engineStatus === 'offline' && <EngineOfflineBanner />}
        <div className="assistant-conversation" aria-live="off">
          {messages.map((item) => <article className="assistant-turn" key={item.id}>
            <p className="assistant-question">{item.question}</p>
            {item.answer ? <section className="assistant-answer" aria-label="Assistant answer">
              <div className="assistant-answer-meta"><span>{item.answer.mode === 'local_fallback' || item.answer.warning ? 'Local fallback' : cloud ? 'Cloud' : 'Local'}</span>{item.answer.synthetic_only && <span>Synthetic only</span>}</div>
              <p>{item.answer.answer}</p>
              {item.answer.warning && <div className="assistant-warning">{item.answer.warning}</div>}
              {item.answer.tool_calls.length > 0 && <details className="assistant-trace"><summary>Tool trace · {item.answer.tool_calls.length} calls</summary>{item.answer.tool_calls.map((call, index) => <section key={`${call.name}-${index}`}><h3>{call.name}</h3><p>Arguments</p><pre>{JSON.stringify(call.arguments, null, 2)}</pre><p>Result</p><pre>{JSON.stringify(call.result, null, 2)}</pre></section>)}</details>}
            </section> : item.error ? <div className="assistant-answer assistant-answer-error"><div className="assistant-answer-meta"><span>{cloud ? 'Local fallback' : 'Local'}</span></div><p>{item.error}</p><button type="button" className="button-quiet assistant-retry" onClick={() => retryQuestion(item)}>Retry question</button></div> : null}
          </article>)}
          {messages.length === 0 && <div className="assistant-suggestions"><span>Suggested questions</span>{suggestions.map((suggestion) => <button key={suggestion} type="button" onClick={() => { setQuestion(suggestion); composer.current?.focus() }}>{suggestion}</button>)}</div>}
        </div>
        <form className={`assistant-composer${busy ? ' is-waiting' : ''}`} onSubmit={(event) => void ask(event)}>
          {busy && <div className="assistant-progress" role="status" aria-label="Assistant is working"><span /></div>}
          <textarea ref={composer} rows={1} value={question} aria-label="Ask TurbineIQ" placeholder="Ask about the synthetic model or selected sample" onChange={(event) => { setQuestion(event.target.value); const field = event.currentTarget; field.style.height = '36px'; field.style.height = `${Math.min(field.scrollHeight, 120)}px` }} onKeyDown={onComposerKeyDown} />
          <button className="assistant-ask-button" type="submit" disabled={busy || !question.trim()}>{busy ? 'Working' : 'Ask'}</button>
        </form>
        <p className="assistant-composer-hint">Enter sends · Shift+Enter adds a line</p>
      </section>
      <ConsentSheet open={consentOpen} onCancel={cancelConsent} onConfirm={confirmConsent} includeDocuments={includeDocuments} onIncludeDocuments={setIncludeDocuments} />
    </div>
  )
}
