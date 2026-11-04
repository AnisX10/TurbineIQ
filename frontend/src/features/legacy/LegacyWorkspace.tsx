import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Bot, Database, Info, Search, Sparkles } from 'lucide-react'
import { api } from '../../api'
import { useTurbineStore } from '../../app/useTurbineStore'
import type { SelectedTwinSelection } from '../../types'
import './LegacyWorkspace.css'

export function LegacyWorkspace({ page }: { page: 'evidence' | 'assistant' }) {
  const { state } = useTurbineStore()
  const [query, setQuery] = useState('Brayton cycle assumptions')
  const [question, setQuestion] = useState('Explain the compressor-efficiency drift result.')
  const [evidence, setEvidence] = useState<Awaited<ReturnType<typeof api.evidence>> | null>(null)
  const [answer, setAnswer] = useState<Awaited<ReturnType<typeof api.ask>> | null>(null)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [cloud, setCloud] = useState(false)
  const [includeExcerpts, setIncludeExcerpts] = useState(false)
  const snapshot = state.run?.snapshots[state.sampleIndex]
  const component = snapshot?.components.find((item) => item.component_id === state.componentId)
  const selectedTwin: SelectedTwinSelection | null = useMemo(() => snapshot && component ? {
    scenario_id: snapshot.scenario_id,
    seed: snapshot.seed,
    sample_index: snapshot.sample_index,
    selected_component_id: component.component_id,
  } : null, [snapshot, component])

  const search = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setMessage('')
    try {
      const result = await api.evidence(query)
      setEvidence(result)
      setMessage(result.no_evidence ? `No supporting passage found for ${query}.` : `${result.evidence.length} cited passages found in local notes.`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'The local search could not complete. No notes were returned; try again.')
    } finally {
      setBusy(false)
    }
  }

  const ask = async () => {
    setBusy(true)
    setMessage('')
    try {
      setAnswer(await api.ask(question, cloud, cloud && includeExcerpts, selectedTwin))
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'The assistant request could not complete. No answer was produced; retry the request.')
    } finally {
      setBusy(false)
    }
  }

  if (page === 'evidence') return (
    <div className="legacy-page evidence-page">
      <p className="legacy-intro">Search local engineering notes. Results include source references.</p>
      <section className="legacy-panel" aria-labelledby="evidence-title">
        <div className="legacy-heading"><h2 id="evidence-title">Local cited retrieval</h2><span><Database size={13} aria-hidden="true" /> No cloud search</span></div>
        <p>Search bundled notes about the simplified model. Results stay in the local service and include a source section.</p>
        <form className="legacy-search" onSubmit={(event) => void search(event)}><Search size={16} aria-hidden="true" /><input value={query} onChange={(event) => setQuery(event.target.value)} aria-label="Search local documents" /><button type="submit" disabled={busy || query.trim().length < 2}>{busy ? 'Searching' : 'Search'}</button></form>
        <div className="legacy-message" role="status">{message}</div>
        <div className="legacy-results">{evidence?.evidence.map((hit, index) => <article key={`${hit.source}-${hit.citation}-${index}`}><div><span>{hit.citation}</span><span>{hit.score.toFixed(2)} relevance</span></div><p>{hit.text}</p><small>{hit.source}{hit.section ? ` · ${hit.section}` : ''}</small></article>)}{evidence?.no_evidence && <p>No supporting passage found for {evidence.query}. The local notes were searched; try a different phrase.</p>}</div>
      </section>
    </div>
  )

  return (
    <div className="legacy-page assistant-page">
      <p className="legacy-intro">Ask about the current synthetic sample. Local mode is the demo-safe default.</p>
      <section className="legacy-panel" aria-labelledby="assistant-title">
        <div className="legacy-heading"><h2 id="assistant-title">TurbineIQ assistant</h2><span><Bot size={14} aria-hidden="true" /> Tool allow-list</span></div>
        <p>Numerical results come from local engineering tools. The assistant cannot connect to equipment or issue actions.</p>
        <div className="assistant-mode" role="group" aria-label="Assistant mode"><button type="button" aria-pressed={!cloud} onClick={() => setCloud(false)}>Local · demo-safe</button><button type="button" aria-pressed={cloud} onClick={() => setCloud(true)}>Cloud</button></div>
        <label className="legacy-label" htmlFor="assistant-question">Question</label><textarea id="assistant-question" rows={4} value={question} onChange={(event) => setQuestion(event.target.value)} />
        {cloud && <div className="cloud-consent"><p>Cloud mode sends the question and tool results to the configured provider.</p><label><input type="checkbox" checked={includeExcerpts} onChange={(event) => setIncludeExcerpts(event.target.checked)} /> Include retrieved document excerpts</label></div>}
        <button className="legacy-submit" type="button" disabled={busy || !question.trim()} onClick={() => void ask()}><Sparkles size={14} aria-hidden="true" />{busy ? 'Working' : 'Ask'}</button>
        {message && <p className="legacy-message" role="status">{message}</p>}
        {answer && <div className="legacy-answer" aria-live="polite"><div><span>{answer.mode.replaceAll('_', ' ')}</span>{answer.warning && <span>{answer.warning}</span>}</div><p>{answer.answer}</p>{answer.tool_calls.length > 0 && <details><summary>Tool trace · {answer.tool_calls.length} calls</summary>{answer.tool_calls.map((call, index) => <pre key={`${call.name}-${index}`}>{call.name} {JSON.stringify(call.arguments)}{'\n'}{JSON.stringify(call.result, null, 2)}</pre>)}</details>}</div>}
        {!answer && !message && <p className="legacy-assistant-note"><Info size={13} aria-hidden="true" /> Responses use the selected synthetic run context.</p>}
      </section>
    </div>
  )
}
