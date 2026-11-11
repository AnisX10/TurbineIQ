import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent as ReactKeyboardEvent } from 'react'
import { ArrowUpRight, Copy, X } from 'lucide-react'
import { api } from '../../api'
import type { AssistantProviderStatus } from '../../api'
import { useTurbineStore } from '../../app/useTurbineStore'
import type { AssistantContextSnapshot, AssistantTurn } from '../../app/storeContext'
import type { AssistantResponse } from '../../types'
import { EngineOfflineBanner } from '../../components/ui/EngineOfflineBanner'
import { generateAssistantSuggestions } from './suggestions'
import './Assistant.css'

interface CitationLink { citation: string; query: string }
let activeAssistantAbort: AbortController | null = null
let nextAssistantTurnId = 0

function citationsFor(answer: AssistantResponse): CitationLink[] {
  const citations: CitationLink[] = []
  for (const call of answer.tool_calls) {
    const rawEvidence = call.result.evidence
    const query = typeof call.arguments.query === 'string' ? call.arguments.query : ''
    if (!Array.isArray(rawEvidence)) continue
    for (const item of rawEvidence) {
      if (item && typeof item === 'object' && 'citation' in item && typeof item.citation === 'string') {
        citations.push({ citation: item.citation, query: query || 'engineering notes' })
      }
    }
  }
  return citations
}

function contextForTurn(turn: AssistantTurn): string[] {
  return [turn.context.scenarioName, `Seed ${turn.context.seed}`, `Sample ${turn.context.sampleIndex + 1}`, turn.context.componentName]
}

function saveCitationState(query: string, citation: string, scenarioId: string, seed: number, sampleIndex: number, closeDock: () => void) {
  const params = new URLSearchParams({ scenario: scenarioId, seed: String(seed), i: String(sampleIndex), q: query, top_k: '4', cite: citation })
  closeDock()
  window.history.pushState(null, '', `#/evidence?${params.toString()}`)
  window.dispatchEvent(new PopStateEvent('popstate'))
}

export function AssistantWorkspace({ variant = 'page', onClose }: { variant?: 'page' | 'dock'; onClose?: () => void }) {
  const { state, dispatch } = useTurbineStore()
  const [providerStatus, setProviderStatus] = useState<AssistantProviderStatus | null>(null)
  const [announcement, setAnnouncement] = useState('')
  const [copiedTurn, setCopiedTurn] = useState<number | null>(null)
  const composer = useRef<HTMLTextAreaElement>(null)
  const snapshot = state.run?.snapshots[state.sampleIndex] ?? null
  const selectedComponentId = state.componentId ?? 'compressor'
  const component = snapshot?.components.find((item) => item.component_id === selectedComponentId)
  const scenarioName = snapshot?.scenario_name
    ?? state.run?.run.scenario_name
    ?? state.scenarios.find((item) => item.scenario_id === state.scenarioId)?.name
    ?? state.scenarioId
  const context: AssistantContextSnapshot = {
    scenarioId: snapshot?.scenario_id ?? state.scenarioId,
    scenarioName,
    seed: snapshot?.seed ?? state.seed,
    sampleIndex: snapshot?.sample_index ?? state.sampleIndex,
    componentId: selectedComponentId,
    componentName: component?.label ?? selectedComponentId,
  }
  const flaggedSamples = state.run?.timeline.filter((point) => point.anomaly_flag).length ?? 0
  const suggestions = generateAssistantSuggestions({
    flaggedSamples,
    sampleNumber: context.sampleIndex + 1,
    componentName: context.componentName,
    residualKw: snapshot?.power_residual_kw ?? null,
  })
  const waiting = state.assistantTurns.some((turn) => turn.streaming)

  useEffect(() => {
    let active = true
    void api.assistantStatus().then((status) => {
      if (active) setProviderStatus(status)
    }).catch(() => { if (active) setProviderStatus(null) })
    return () => { active = false }
  }, [])

  const openConsent = () => dispatch({
    type: 'assistant-consent-open',
    value: { open: true, resumeDock: variant === 'dock' },
  })

  const runQuestion = useCallback(async (turn: AssistantTurn) => {
    const controller = new AbortController()
    activeAssistantAbort = controller
    dispatch({ type: 'assistant-turn-patch', value: { id: turn.id, patch: { streaming: true, error: undefined, partialAnswer: '', toolProgress: 'Preparing the selected context.' } } })
    let partial = ''
    try {
      const answer = await api.streamAssistant(
        turn.question,
        state.assistantMode === 'cloud',
        state.assistantMode === 'cloud' && state.assistantIncludeDocuments,
        {
          scenario_id: turn.context.scenarioId,
          seed: turn.context.seed,
          sample_index: turn.context.sampleIndex,
          selected_component_id: turn.context.componentId,
        },
        (eventName, payload) => {
          if (eventName === 'status') {
            dispatch({ type: 'assistant-turn-patch', value: { id: turn.id, patch: { toolProgress: (payload as { message: string }).message } } })
          } else if (eventName === 'tool_start') {
            const name = (payload as { name: string }).name
            dispatch({ type: 'assistant-turn-patch', value: { id: turn.id, patch: { toolProgress: `Running ${name}...` } } })
          } else if (eventName === 'tool_result') {
            const name = (payload as { name: string }).name
            dispatch({ type: 'assistant-turn-patch', value: { id: turn.id, patch: { toolProgress: `Completed ${name}.` } } })
          } else if (eventName === 'token') {
            partial += (payload as { text: string }).text
            dispatch({ type: 'assistant-turn-patch', value: { id: turn.id, patch: { partialAnswer: partial } } })
          }
        },
        controller.signal,
      )
      dispatch({ type: 'assistant-turn-patch', value: { id: turn.id, patch: { answer, partialAnswer: answer.answer, streaming: false, toolProgress: undefined, error: undefined } } })
      setAnnouncement(`Answer ${turn.id} is ready.`)
    } catch (error) {
      const message = controller.signal.aborted
        ? 'Stopped before the answer was complete.'
        : error instanceof Error ? error.message : 'The assistant request failed. Retry the question.'
      dispatch({ type: 'assistant-turn-patch', value: { id: turn.id, patch: { streaming: false, toolProgress: undefined, error: message } } })
    } finally {
      if (activeAssistantAbort === controller) activeAssistantAbort = null
      if (variant === 'page' || state.assistantOpen) composer.current?.focus()
    }
  }, [dispatch, state.assistantMode, state.assistantIncludeDocuments, state.assistantOpen, variant])

  const submit = (event?: FormEvent) => {
    event?.preventDefault()
    const text = state.assistantDraft.trim()
    if (!text || waiting) return
    const turn: AssistantTurn = { id: ++nextAssistantTurnId, question: text, context, streaming: true }
    dispatch({ type: 'assistant-turn-add', value: turn })
    dispatch({ type: 'assistant-draft', value: '' })
    if (composer.current) composer.current.style.height = '36px'
    void runQuestion(turn)
  }

  const retry = (turn: AssistantTurn) => {
    if (!waiting) void runQuestion(turn)
  }
  const stop = () => activeAssistantAbort?.abort()
  const onComposerKeyDown = (event: ReactKeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submit() }
  }
  const askCloud = () => {
    if (state.assistantConsentAccepted) dispatch({ type: 'assistant-mode', value: 'cloud' })
    else openConsent()
  }
  const copyAnswer = async (turn: AssistantTurn) => {
    if (!turn.answer) return
    try {
      await navigator.clipboard.writeText(turn.answer.answer)
      setCopiedTurn(turn.id)
      window.setTimeout(() => setCopiedTurn(null), 1500)
    } catch { setCopiedTurn(null) }
  }

  return (
    <div className={`assistant-page${variant === 'dock' ? ' assistant-dock-page' : ''}`} id={variant === 'page' ? 'route-outlet' : undefined}>
      <section className="assistant-workspace" aria-label="Engineering assistant">
        <div className="assistant-mode-row">
          <div className="assistant-heading-inline">
            {variant === 'dock' && <h2 id="assistant-dock-title">Ask TurbineIQ</h2>}
            {variant === 'dock' && onClose && <button className="assistant-dock-close" type="button" aria-label="Close assistant" onClick={onClose}><X size={17} aria-hidden="true" /></button>}
            {variant === 'page' && <h2>Ask about the current sample</h2>}
          </div>
          <div className="assistant-mode-segmented" role="group" aria-label="Assistant deployment mode">
            <button type="button" aria-pressed={state.assistantMode === 'local'} onClick={() => dispatch({ type: 'assistant-mode', value: 'local' })}>Local <span>demo-safe</span></button>
            <button type="button" aria-pressed={state.assistantMode === 'cloud'} onClick={askCloud}>Cloud</button>
          </div>
        </div>
        <div className="assistant-context" aria-label="Current server-recomputed context">
          <span>{scenarioName}</span><span>Seed {context.seed}</span><span>Sample {context.sampleIndex + 1}</span><span>{context.componentName}</span>
        </div>
        {state.engineStatus === 'offline' && <EngineOfflineBanner />}
        <div className="assistant-conversation" aria-live="off">
          {state.assistantTurns.map((turn) => <article className="assistant-turn" key={turn.id}>
            <p className="assistant-question">{turn.question}</p>
            {turn.answer ? <section className="assistant-answer" aria-label="Assistant answer">
              <div className="assistant-answer-meta">
                <span>{turn.answer.mode === 'local_fallback' || turn.answer.warning ? 'Local fallback' : turn.answer.mode === 'cloud' ? `${providerStatus?.provider ?? 'Cloud'} · ${providerStatus?.model ?? 'configured model'}` : 'Local'}</span>
                {turn.answer.synthetic_only && <span>Synthetic only</span>}
              </div>
              <p>{turn.answer.answer}</p>
              <div className="assistant-turn-context" aria-label="Context used for this answer">{contextForTurn(turn).map((chip) => <span key={chip}>{chip}</span>)}</div>
              {turn.answer.warning && <div className="assistant-warning">{turn.answer.warning}</div>}
              <div className="assistant-answer-actions"><button className="button-quiet assistant-copy" type="button" onClick={() => void copyAnswer(turn)}><Copy size={13} aria-hidden="true" />{copiedTurn === turn.id ? 'Copied' : 'Copy answer'}</button></div>
              {citationsFor(turn.answer).length > 0 && <div className="assistant-citations" aria-label="Citations">{citationsFor(turn.answer).map((link, index) => <button type="button" className="citation-chip" key={`${link.citation}-${index}`} onClick={() => saveCitationState(link.query, link.citation, turn.context.scenarioId, turn.context.seed, turn.context.sampleIndex, () => dispatch({ type: 'assistant-open', value: false }))}>{link.citation}<ArrowUpRight size={12} aria-hidden="true" /></button>)}</div>}
              {turn.answer.tool_calls.length > 0 && <details className="assistant-trace"><summary>Tool trace · {turn.answer.tool_calls.length} calls</summary>{turn.answer.tool_calls.map((call, index) => <section key={`${call.name}-${index}`}><h3>{call.name}</h3><p>Arguments</p><pre>{JSON.stringify(call.arguments, null, 2)}</pre><p>Result</p><pre>{JSON.stringify(call.result, null, 2)}</pre></section>)}</details>}
            </section> : turn.streaming ? <section className="assistant-answer" aria-label="Assistant response in progress">
              <div className="assistant-answer-meta"><span>{state.assistantMode === 'cloud' ? `${providerStatus?.provider ?? 'Cloud'} · ${providerStatus?.model ?? 'configured model'}` : 'Local'}</span><span>{turn.toolProgress || 'Working'}</span></div>
              <p>{turn.partialAnswer}</p><button type="button" className="button-quiet assistant-stop" onClick={stop}>Stop</button>
            </section> : turn.error ? <div className="assistant-answer assistant-answer-error"><div className="assistant-answer-meta"><span>{turn.error.includes('fallback') ? 'Local fallback' : state.assistantMode === 'cloud' ? 'Cloud' : 'Local'}</span></div><p>{turn.error}</p><button type="button" className="button-quiet assistant-retry" onClick={() => retry(turn)}>Retry question</button></div> : null}
          </article>)}
          {state.assistantTurns.length === 0 && <div className="assistant-suggestions"><span>Suggested questions</span>{suggestions.map((suggestion) => <button key={suggestion} type="button" onClick={() => { dispatch({ type: 'assistant-draft', value: suggestion }); composer.current?.focus() }}>{suggestion}</button>)}</div>}
        </div>
        <form className={`assistant-composer${waiting ? ' is-waiting' : ''}`} onSubmit={submit}>
          {waiting && <div className="assistant-progress" role="status" aria-label="Assistant is working"><span /></div>}
          <textarea ref={composer} data-sheet-autofocus={variant === 'dock' ? '' : undefined} rows={1} maxLength={1000} value={state.assistantDraft} aria-label="Ask TurbineIQ" placeholder="Ask about the synthetic model or selected sample" onChange={(event) => { dispatch({ type: 'assistant-draft', value: event.target.value }); const field = event.currentTarget; field.style.height = '36px'; field.style.height = `${Math.min(field.scrollHeight, 120)}px` }} onKeyDown={onComposerKeyDown} />
          <button className="assistant-ask-button" type="submit" disabled={waiting || !state.assistantDraft.trim()}>{waiting ? 'Working' : 'Ask'}</button>
        </form>
        {waiting && <button type="button" className="button-quiet assistant-stop-all" onClick={stop}>Stop response</button>}
        <p className="assistant-composer-hint">Enter sends · Shift+Enter adds a line</p>
        <p className="sr-only" aria-live="polite" aria-atomic="true">{announcement}</p>
      </section>
    </div>
  )
}
