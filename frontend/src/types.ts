export interface TwinMetric {
  key: string
  label: string
  value: number | boolean
  unit: string
  provenance: string
  reference_value: number | null
}

export interface TwinComponentState {
  component_id: string
  label: string
  status: string
  status_label: string
  summary: string
  metrics: TwinMetric[]
}

export interface TwinSnapshot {
  asset_id: string
  sample_index: number
  timestamp_utc: string
  scenario_id: string
  scenario_name: string
  seed: number
  ambient_temperature_c: number
  ambient_pressure_kpa: number
  compressor_efficiency_assumption: number
  synthetic_true_compressor_efficiency: number
  compressor_discharge_temperature_k: number
  reference_compressor_discharge_temperature_k: number
  turbine_inlet_temperature_k: number
  exhaust_temperature_k: number
  reference_exhaust_temperature_k: number
  model_electrical_power_kw: number
  synthetic_truth_electrical_power_kw: number
  synthetic_observed_power_kw: number
  power_residual_kw: number
  residual_percent: number
  sensor_fault_label: string
  sensor_fault_injected: boolean
  residual_screen_flag: boolean
  screen_status: string
  scenario_perturbation_label: string
  components: TwinComponentState[]
  data_provenance: string
}

export interface ScenarioDefinition {
  scenario_id: string
  name: string
  description: string
  synthetic_only: boolean
  sample_interval_minutes: number
}

export interface TimelinePoint {
  timestamp_utc: string
  model_electrical_power_kw: number
  synthetic_truth_electrical_power_kw: number
  observed_electrical_power_kw: number
  power_residual_kw: number
  anomaly_flag: boolean
  robust_z_score: number
  [key: string]: string | number | boolean | null
}

export interface TwinRunMetadata {
  asset_id: string
  scenario_id: string
  scenario_name: string
  scenario_description: string
  seed: number
  sample_count: number
  sample_interval_minutes: number
  model_name: string
  synthetic_only: boolean
  data_provenance: string
}

export interface TwinRunPayload {
  run: TwinRunMetadata
  snapshot: TwinSnapshot
  snapshots: TwinSnapshot[]
  timeline: TimelinePoint[]
}

export interface EvidenceHit {
  text: string
  citation: string
  source: string
  page_number: number | null
  section: string | null
  score: number
}

export interface EvidenceResponse {
  query: string
  mode: string
  evidence: EvidenceHit[]
  no_evidence: boolean
}

export interface AssistantResponse {
  answer: string
  mode: string
  warning: string | null
  tool_calls: Array<{ name: string; arguments: Record<string, unknown>; result: Record<string, unknown> }>
  synthetic_only: boolean
}

export interface SelectedTwinSelection {
  scenario_id: string
  seed: number
  sample_index: number
  selected_component_id: string
}
