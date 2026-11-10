import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Search } from 'lucide-react'
import { api } from '../../api'
import { useTurbineStore } from '../../app/useTurbineStore'
import type { EvidenceHit } from '../../types'
import { EngineOfflineBanner } from '../../components/ui/EngineOfflineBanner'
import './EvidencePanel.css'

function updateSearchUrl(query: string, topK: number) {
  const [path, rawQuery = ''] = window.location.hash.replace(/^#/, '').split('?')
  const params = new URLSearchParams(rawQuery)
  params.set('q', query)
  params.set('top_k', String(topK))
  window.history.pushState(null, '', `#${path || '/evidence'}?${params.toString()}`)
  window.dispatchEvent(new PopStateEvent('popstate'))
}

export function EvidencePanel({ initialQuery = '' }: { initialQuery?: string }) {
  const { state } = useTurbineStore()
  const routeQuery = state.evidenceQuery ?? ''
  const draftSource = `${routeQuery}\u001f${initialQuery}\u001f${state.evidenceTopK ?? 4}`
  const [draft, setDraft] = useState(() => ({ source: draftSource, query: routeQuery || initialQuery, topK: state.evidenceTopK ?? 4 }))
  const draftIsCurrent = draft.source === draftSource
  const query = draftIsCurrent ? draft.query : routeQuery || initialQuery
  const topK = draftIsCurrent ? draft.topK : state.evidenceTopK ?? 4
  const setQuery = (value: string) => setDraft({ source: draftSource, query: value, topK })
  const setTopK = (value: number) => setDraft({ source: draftSource, query, topK: value })
  const [evidence, setEvidence] = useState<Awaited<ReturnType<typeof api.evidence>> | null>(null)
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [invalid, setInvalid] = useState(false)
  const lastAutoSearchKey = useRef('')
  const sorted = useMemo(() => [...(evidence?.evidence ?? [])].sort((a, b) => b.score - a.score), [evidence])
  const selected: EvidenceHit | null = sorted[selectedIndex] ?? null
  const maxScore = Math.max(0, ...sorted.map((hit) => hit.score))

  const search = useCallback(async (event?: FormEvent) => {
    event?.preventDefault()
    const cleanQuery = query.trim()
    if (cleanQuery.length < 2 || cleanQuery.length > 300 || !Number.isInteger(topK) || topK < 1 || topK > 8) {
      setInvalid(true)
      return
    }
    setInvalid(false)
    setBusy(true)
    setError('')
    lastAutoSearchKey.current = `${cleanQuery}\u001f${topK}`
    updateSearchUrl(cleanQuery, topK)
    try {
      const result = await api.evidence(cleanQuery, topK)
      setEvidence(result)
      const ordered = [...result.evidence].sort((left, right) => right.score - left.score)
      const citationIndex = state.evidenceCitation
        ? ordered.findIndex((hit) => hit.citation === state.evidenceCitation)
        : -1
      setSelectedIndex(citationIndex >= 0 ? citationIndex : 0)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The local evidence request failed.')
    } finally {
      setBusy(false)
    }
  }, [query, topK, state.evidenceCitation])

  useEffect(() => {
    const cleanQuery = (routeQuery || initialQuery).trim()
    const currentTopK = state.evidenceTopK ?? 4
    const key = `${cleanQuery}\u001f${currentTopK}`
    if (cleanQuery.length < 2 || query.trim() !== cleanQuery || topK !== currentTopK || lastAutoSearchKey.current === key) return
    lastAutoSearchKey.current = key
    void search()
  }, [routeQuery, initialQuery, state.evidenceTopK, query, topK, search])

  return (
    <section className="evidence-workspace" aria-label="Local technical evidence">
      <form className="evidence-search" onSubmit={(event) => void search(event)}>
        <label className="evidence-query"><Search size={16} aria-hidden="true" /><span className="sr-only">Search local documents</span><input value={query} maxLength={300} onChange={(event) => setQuery(event.target.value)} placeholder="Search local technical notes" aria-invalid={invalid && query.trim().length < 2} /></label>
        <label className="evidence-top-k"><span>Top</span><input aria-label="Maximum evidence results" type="number" min="1" max="8" step="1" value={topK} onChange={(event) => setTopK(Number(event.target.value))} /></label>
        <button type="submit" disabled={busy || query.trim().length < 2}>{busy ? 'Searching…' : 'Search'}</button>
      </form>
      {invalid && <p className="evidence-error" role="alert">Enter a query of 2 to 300 characters and a result count from 1 to 8.</p>}
      {state.engineStatus === 'offline' && <EngineOfflineBanner />}
      {error && <div className="request-banner" role="alert"><span>{error}</span><button type="button" className="button-quiet evidence-retry" onClick={() => void search()}>Retry</button></div>}
      <div className="evidence-panels">
        <section className="evidence-results panel" aria-labelledby="evidence-results-title">
          <div className="evidence-panel-heading"><h2 id="evidence-results-title">Results</h2><span>{evidence ? `${sorted.length} passages` : 'Local lexical retrieval'}</span></div>
          {busy && <div className="evidence-skeleton" aria-label="Searching local documents"><i /><i /><i /><i /></div>}
          {!busy && !evidence && !error && <p className="evidence-placeholder">Search local engineering notes to review cited passages.</p>}
          {!busy && evidence?.no_evidence && <div className="evidence-no-results"><p>No supporting passage found for {evidence.query}.</p><small>Searched local technical documents using {evidence.mode}.</small></div>}
          {!busy && sorted.length > 0 && <div className="evidence-result-list" role="listbox" aria-label="Evidence search results">
            {sorted.map((hit, index) => <button id={`evidence-result-${index}`} key={`${hit.source}-${hit.citation}-${index}`} type="button" role="option" aria-selected={index === selectedIndex} className={`evidence-result ${index === selectedIndex ? 'is-selected' : ''}`} onKeyDown={(event) => {
              if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
              event.preventDefault()
              const next = (index + (event.key === 'ArrowDown' ? 1 : sorted.length - 1)) % sorted.length
              setSelectedIndex(next)
              document.getElementById(`evidence-result-${next}`)?.focus()
            }} onClick={() => setSelectedIndex(index)}>
              <span className="evidence-result-top"><span className="evidence-result-title">{hit.source}</span><span className="citation-chip">{hit.citation}</span></span>
              <span className="evidence-score-row"><span className="evidence-score-track"><span style={{ width: `${maxScore > 0 ? Math.max(0, hit.score / maxScore * 100) : 0}%` }} /></span><span className="evidence-score">{hit.score.toFixed(2)}</span></span>
            </button>)}
          </div>}
        </section>
        <section className="evidence-reader panel" aria-labelledby="evidence-reader-title">
          <div className="evidence-panel-heading"><h2 id="evidence-reader-title">Reader</h2>{selected && <span className="citation-chip">{selected.citation}</span>}</div>
          {selected ? <article className="evidence-excerpt"><p>{selected.text}</p><dl><div><dt>Source</dt><dd>{selected.source}</dd></div>{selected.section && <div><dt>Section</dt><dd>{selected.section}</dd></div>}{selected.page_number !== null && <div><dt>Page</dt><dd>{selected.page_number}</dd></div>}<div><dt>Retrieval</dt><dd>{evidence?.mode}</dd></div></dl></article> : <p className="evidence-placeholder">Select a result to read its cited excerpt.</p>}
        </section>
      </div>
    </section>
  )
}
