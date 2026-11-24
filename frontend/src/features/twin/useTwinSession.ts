import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { simApi, twinApi } from '../../api'
import { commandSummary, mergeSamples } from '../operate/simLogic'
import type { SimState } from '../operate/simTypes'
import type { Decision, SupervisorMode, SupervisorSummary } from './supervisorTypes'
import { MODE_LABELS, STATUS_LABELS, modeSwitchReducer } from './twinLogic'

export interface TwinLogEntry { id: number; t_s: number; text: string; kind: 'command' | 'alarm' | 'info' | 'decision' }

export const TWIN_SESSION_KEY = 'turbineiq-sim-session'
const TICK_MS = 500
const MAX_SAMPLES = 900

export function readStoredSession(): string | null {
  try {
    return window.sessionStorage.getItem(TWIN_SESSION_KEY)
  } catch {
    return null
  }
}

export function storeSession(id: string | null): void {
  try {
    if (id) window.sessionStorage.setItem(TWIN_SESSION_KEY, id)
    else window.sessionStorage.removeItem(TWIN_SESSION_KEY)
  } catch {
    return
  }
}

const message = (cause: unknown, fallback: string) => (cause instanceof Error ? cause.message : fallback)

/** The live unit with its supervisor: state, recent samples, supervisor summary and actions. */
export function useTwinSession() {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [state, setState] = useState<SimState | null>(null)
  const [samples, setSamples] = useState<SimState[]>([])
  const [summary, setSummary] = useState<SupervisorSummary | null>(null)
  const [demands, setDemands] = useState<Array<{ t: number; mw: number | null }>>([])
  const [log, setLog] = useState<TwinLogEntry[]>([])
  const [running, setRunning] = useState(false)
  const [speed, setSpeed] = useState(10)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [resuming, setResuming] = useState(() => readStoredSession() !== null)
  const [mode, dispatchMode] = useReducer(modeSwitchReducer, { current: null, requested: null, error: null })
  const inFlight = useRef(false)
  const logId = useRef(0)
  const seenAlarms = useRef(0)
  const seenDecisions = useRef(new Map<number, string>())

  const addLog = useCallback((t_s: number, text: string, kind: TwinLogEntry['kind']) => {
    logId.current += 1
    const entry = { id: logId.current, t_s, text, kind }
    setLog((previous) => [entry, ...previous].slice(0, 120))
  }, [])

  const noteState = useCallback((next: SimState) => {
    for (const alarm of next.alarms) {
      const key = Math.round(alarm.t_s * 1000)
      if (key > seenAlarms.current) {
        seenAlarms.current = key
        addLog(alarm.t_s, alarm.message, 'alarm')
      }
    }
  }, [addLog])

  const noteSummary = useCallback((next: SupervisorSummary | undefined | null) => {
    if (!next) return
    setSummary(next)
    dispatchMode({ type: 'server', mode: next.mode })
    setDemands((previous) => {
      const last = previous[previous.length - 1]
      if (last && last.mw === next.demand_mw) return previous
      return [...previous, { t: next.status?.t_s ?? 0, mw: next.demand_mw }].slice(-200)
    })
    const decisions: Decision[] = [...next.recent_decisions, ...next.open_decisions]
    for (const d of decisions) {
      const seen = seenDecisions.current.get(d.id)
      if (seen === d.status) continue
      seenDecisions.current.set(d.id, d.status)
      const t = d.status === 'pending' || d.status === 'escalated' || d.resolved_t_s === null ? d.t_s : d.resolved_t_s
      addLog(t, `Decision ${d.id} · ${STATUS_LABELS[d.status] ?? d.status}: ${d.summary}`, 'decision')
    }
  }, [addLog])

  const reset = useCallback(() => {
    setSamples([])
    setLog([])
    setDemands([])
    seenAlarms.current = 0
    seenDecisions.current = new Map()
  }, [])

  // Pick up the unit this browser tab already runs (shared with Operate), if it still exists.
  useEffect(() => {
    const stored = readStoredSession()
    if (!stored) return
    let active = true
    ;(async () => {
      try {
        const [current, history] = await Promise.all([twinApi.state(stored), twinApi.history(stored, MAX_SAMPLES)])
        let sup: SupervisorSummary | null = null
        try {
          sup = await twinApi.supervisor(stored)
        } catch {
          sup = await twinApi.attach(stored, 'advisory')
        }
        if (!active) return
        setSessionId(stored)
        setState(current)
        setSamples(history.samples.length ? history.samples : [current])
        noteSummary(sup)
        addLog(current.t_s, 'Resumed the unit running in this tab', 'info')
      } catch {
        storeSession(null)
      } finally {
        if (active) setResuming(false)
      }
    })()
    return () => { active = false }
  }, [addLog, noteSummary])

  const create = useCallback(async (supervisorMode: SupervisorMode) => {
    setBusy(true)
    setError('')
    try {
      const created = await twinApi.create(supervisorMode, { seed: 1 })
      setRunning(false)
      reset()
      setSessionId(created.session_id)
      storeSession(created.session_id)
      setState(created.state)
      setSamples([created.state])
      dispatchMode({ type: 'confirmed', mode: supervisorMode })
      noteSummary(created.supervisor)
      addLog(created.state.t_s, `Simulated unit created at standstill, layer in ${MODE_LABELS[supervisorMode].toLowerCase()} mode`, 'info')
    } catch (cause) {
      setError(message(cause, 'Could not create the simulated unit.'))
    } finally {
      setBusy(false)
    }
  }, [addLog, noteSummary, reset])

  const run = useCallback(async <T,>(work: (id: string) => Promise<T>, fallback: string): Promise<T | null> => {
    if (!sessionId) return null
    setBusy(true)
    setError('')
    try {
      return await work(sessionId)
    } catch (cause) {
      setError(message(cause, fallback))
      return null
    } finally {
      setBusy(false)
    }
  }, [sessionId])

  const refreshSummary = useCallback(async (id: string) => {
    try {
      noteSummary(await twinApi.supervisor(id))
    } catch {
      return
    }
  }, [noteSummary])

  const send = useCallback(async (command: string, params: Record<string, unknown> = {}) => {
    const result = await run((id) => simApi.command(id, command, params), 'The command failed.')
    if (!result || !sessionId) return false
    setState(result.state)
    setSamples((previous) => mergeSamples(previous, [result.state], MAX_SAMPLES))
    addLog(result.state.t_s, commandSummary(command, params), 'command')
    noteState(result.state)
    void refreshSummary(sessionId)
    return true
  }, [run, sessionId, addLog, noteState, refreshSummary])

  const applyResult = useCallback((result: { state: SimState; supervisor: SupervisorSummary }) => {
    setState(result.state)
    setSamples((previous) => mergeSamples(previous, [result.state], MAX_SAMPLES))
    noteSummary(result.supervisor)
    noteState(result.state)
  }, [noteSummary, noteState])

  const setDemand = useCallback(async (mw: number) => {
    const result = await run((id) => twinApi.setDemand(id, mw, true), 'The demand was not accepted.')
    if (!result) return false
    applyResult(result)
    addLog(result.state.t_s, `Demand ${mw.toFixed(1)} MW (setpoint moved to it)`, 'command')
    return true
  }, [run, applyResult, addLog])

  const changeMode = useCallback(async (next: SupervisorMode) => {
    if (!sessionId || mode.requested !== null || next === mode.current) return
    dispatchMode({ type: 'request', mode: next })
    try {
      const result = await twinApi.setMode(sessionId, next)
      dispatchMode({ type: 'confirmed', mode: result.mode })
      noteSummary(result)
      addLog(result.status?.t_s ?? 0, `Mode set to ${MODE_LABELS[result.mode].toLowerCase()}`, 'command')
    } catch (cause) {
      dispatchMode({ type: 'failed', message: message(cause, 'The mode did not change.') })
    }
  }, [sessionId, mode, noteSummary, addLog])

  const decide = useCallback(async (decisionId: number, accept: boolean) => {
    const result = await run((id) => (accept ? twinApi.accept(id, decisionId) : twinApi.reject(id, decisionId)), 'The decision could not be recorded.')
    if (!result) return false
    applyResult(result)
    return true
  }, [run, applyResult])

  const trustThermocouple = useCallback(async () => {
    const result = await run((id) => twinApi.trustThermocouple(id), 'The thermocouple could not be returned to the control.')
    if (!result) return false
    applyResult(result)
    addLog(result.state.t_s, 'Thermocouple confirmed repaired; control returned to it', 'command')
    return true
  }, [run, applyResult, addLog])

  const advance = useCallback(async (seconds: number) => {
    if (!sessionId) return
    const result = await twinApi.advance(sessionId, seconds)
    setState(result.state)
    setSamples((previous) => mergeSamples(previous, result.samples, MAX_SAMPLES))
    noteState(result.state)
    noteSummary(result.supervisor)
  }, [sessionId, noteState, noteSummary])

  useEffect(() => {
    if (!running || !sessionId) return
    const timer = window.setInterval(async () => {
      if (inFlight.current) return
      inFlight.current = true
      try {
        await advance((TICK_MS / 1000) * speed)
      } catch (cause) {
        setError(message(cause, 'The simulation stopped responding.'))
        setRunning(false)
      } finally {
        inFlight.current = false
      }
    }, TICK_MS)
    return () => window.clearInterval(timer)
  }, [running, sessionId, speed, advance])

  return {
    sessionId, state, samples, summary, demands, log, running, setRunning, speed, setSpeed, error, busy, resuming,
    mode, create, send, setDemand, changeMode, decide, trustThermocouple, advance,
  }
}

export type TwinSession = ReturnType<typeof useTwinSession>
