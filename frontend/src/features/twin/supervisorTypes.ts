/** Types of the WP5 supervisor as the simulation API reports it (`/api/sim/sessions/{id}/supervisor`). */
import type { SimState } from '../operate/simTypes'

export type SupervisorMode = 'manual' | 'advisory' | 'autonomous'
export const SUPERVISOR_MODES: readonly SupervisorMode[] = ['manual', 'advisory', 'autonomous']

/** Health deltas against the clean engine (fractions; negative is worse). */
export interface HealthDeltas {
  compressor_flow: number
  compressor_efficiency: number
  turbine_efficiency: number
}

export interface TwinStatus {
  t_s: number
  loaded: boolean
  steady: boolean
  health: HealthDeltas
  health_std: HealthDeltas
  estimator_updates: number
  mismatch_index: number | null
  residual_mean: Record<string, number>
  exhaust_residual_k: number | null
  exhaust_scatter_k: number | null
  exhaust_suspect: boolean
  exhaust_reason: string | null
  model_exhaust_k: number | null
  fouling_rate_per_h: number | null
}

export interface GuardCheck {
  name: string
  passed: boolean
  value: number | string | null
  limit: number | string | null
  detail: string
}

export interface GuardVerdict {
  approved: boolean
  reason: string
  checks: GuardCheck[]
  forward: Record<string, unknown> | null
}

export type DecisionProblem = 'load_setpoint' | 'compressor_wash' | 'exhaust_feedback'
export type DecisionStatus = 'applied' | 'pending' | 'escalated' | 'accepted' | 'rejected' | 'expired' | 'superseded'

export interface Decision {
  id: number
  t_s: number
  problem: DecisionProblem | string
  mode: SupervisorMode
  summary: string
  actions: Array<{ command: string; params: Record<string, unknown> }>
  objective: Record<string, unknown>
  verdict: GuardVerdict
  status: DecisionStatus | string
  reason: string
  resolved_t_s: number | null
  resolved_by: string | null
}

export interface LoadCandidate {
  load_mw: number
  igv: 'auto' | number
  fuel_kg_s: number
  exhaust_k: number
  heat_rate_kj_per_kwh: number
  feasible: boolean
}

export interface LoadEvaluation {
  t_s: number
  band_mw: [number, number]
  current: { load_mw: number; igv: 'auto' | number; exhaust_k: number; heat_rate_kj_per_kwh: number; within_limits: boolean }
  screen_exhaust_limit_k: number
  candidates: LoadCandidate[]
}

export interface WashEvaluation {
  t_s: number
  loss_usd_per_h: number
  loss_growth_usd_per_h2: number
  threshold_usd_per_h: number
  optimal_interval_h: number | null
  fouling_flow_delta: number
  wash_now: boolean
}

export interface SupervisorSummary {
  mode: SupervisorMode
  demand_mw: number | null
  band_mw: [number, number] | null
  substitute_active: boolean
  procedure: string[]
  status: TwinStatus | null
  open_decisions: Decision[]
  last_load_evaluation: LoadEvaluation | null
  last_wash_evaluation: WashEvaluation | null
  counters: Record<string, number>
  decisions_total: number
  recent_decisions: Decision[]
}

export interface SupervisedCreated {
  session_id: string
  state: SimState
  supervisor?: SupervisorSummary
}

export interface SupervisedAdvance { state: SimState; samples: SimState[]; supervisor?: SupervisorSummary }
export interface SupervisorActionResult { supervisor: SupervisorSummary; state: SimState }
export interface DecisionResult extends SupervisorActionResult { decision: Decision }
export interface DecisionLog { decisions: Decision[]; total: number }
