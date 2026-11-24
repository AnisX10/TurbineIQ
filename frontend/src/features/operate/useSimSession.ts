import { useCallback, useEffect, useRef, useState } from 'react'
import { simApi } from '../../api'
import { commandSummary, mergeSamples } from './simLogic'
import { readStoredSession, storeSession } from '../twin/useTwinSession'
import type { SimConfig, SimState } from './simTypes'

export interface LogEntry { id: number; t_s: number; text: string; kind: 'command' | 'alarm' | 'info' }

const TICK_MS = 500

export function useSimSession() {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [state, setState] = useState<SimState | null>(null)
  const [samples, setSamples] = useState<SimState[]>([])
  const [log, setLog] = useState<LogEntry[]>([])
  const [running, setRunning] = useState(false)
  const [speed, setSpeed] = useState(10)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const inFlight = useRef(false)
  const logId = useRef(0)
  const seenAlarms = useRef(0)

  const addLog = useCallback((t_s: number, text: string, kind: LogEntry['kind']) => {
    logId.current += 1
    const entry = { id: logId.current, t_s, text, kind }
    setLog((previous) => [entry, ...previous].slice(0, 60))
  }, [])

  const noteAlarms = useCallback((next: SimState) => {
    for (const alarm of next.alarms) {
      const key = Math.round(alarm.t_s * 1000)
      if (key > seenAlarms.current) {
        seenAlarms.current = key
        addLog(alarm.t_s, alarm.message, 'alarm')
      }
    }
  }, [addLog])

  const create = useCallback(async (config: Partial<SimConfig>) => {
    setBusy(true)
    setError('')
    try {
      const created = await simApi.create(config)
      setRunning(false)
      setSessionId(created.session_id)
      storeSession(created.session_id)
      setState(created.state)
      setSamples([created.state])
      setLog([])
      seenAlarms.current = 0
      addLog(created.state.t_s, 'Simulated unit created at standstill', 'info')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not create the simulated unit.')
    } finally {
      setBusy(false)
    }
  }, [addLog])

  // Pick up the unit this tab already runs (the twin console and Operate share it).
  useEffect(() => {
    const stored = readStoredSession()
    if (!stored) return
    let active = true
    Promise.all([simApi.state(stored), simApi.history(stored)]).then(([current, history]) => {
      if (!active) return
      setSessionId(stored)
      setState(current)
      setSamples(history.samples.length ? history.samples : [current])
      addLog(current.t_s, 'Resumed the unit running in this tab', 'info')
    }).catch(() => storeSession(null))
    return () => { active = false }
  }, [addLog])

  const send = useCallback(async (command: string, params: Record<string, unknown> = {}) => {
    if (!sessionId) return false
    setBusy(true)
    setError('')
    try {
      const result = await simApi.command(sessionId, command, params)
      setState(result.state)
      setSamples((previous) => mergeSamples(previous, [result.state]))
      addLog(result.state.t_s, commandSummary(command, params), 'command')
      noteAlarms(result.state)
      return true
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The command failed.')
      return false
    } finally {
      setBusy(false)
    }
  }, [sessionId, addLog, noteAlarms])

  useEffect(() => {
    if (!running || !sessionId) return
    const timer = window.setInterval(async () => {
      if (inFlight.current) return
      inFlight.current = true
      try {
        const result = await simApi.advance(sessionId, (TICK_MS / 1000) * speed)
        setState(result.state)
        setSamples((previous) => mergeSamples(previous, result.samples))
        noteAlarms(result.state)
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : 'The simulation stopped responding.')
        setRunning(false)
      } finally {
        inFlight.current = false
      }
    }, TICK_MS)
    return () => window.clearInterval(timer)
  }, [running, sessionId, speed, noteAlarms])

  return { sessionId, state, samples, log, running, setRunning, speed, setSpeed, error, busy, create, send }
}
