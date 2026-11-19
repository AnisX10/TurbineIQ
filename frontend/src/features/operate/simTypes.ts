export type SimGrid = 'infinite_bus' | 'island'

export interface SimConfig {
  seed: number
  ambient_temperature_c: number
  grid: SimGrid
  grid_frequency_hz: number
  island_load_mw: number
  measurement_noise: boolean
  record_interval_s: number
}

export interface SimAlarm { t_s: number; message: string }

/** What the instruments report (sensor faults applied, then measurement noise). */
export interface SimMeasured {
  electrical_power_mw: number
  exhaust_temperature_k: number
  speed_pu: number
  compressor_discharge_temperature_k: number
  compressor_discharge_pressure_kpa: number
  fuel_flow_kg_s: number
}

export type SimChannel =
  | 'electrical_power'
  | 'exhaust_temperature'
  | 'speed'
  | 'compressor_discharge_temperature'
  | 'compressor_discharge_pressure'
  | 'fuel_flow'
export type SimSensorMode = 'bias' | 'drift' | 'stuck' | 'noise'
export type SimDegradationKind = 'compressor_fouling' | 'turbine_erosion'

export interface SimSensorFault { mode: SimSensorMode; magnitude: number | null; unit: string; since_s: number; stuck_value?: number }

/** Ground truth of injected faults. A detector under test must not read this. */
export interface SimInjectedFaults {
  degradation: Partial<Record<SimDegradationKind, { severity_pct: number; rate_pct_per_h: number }>>
  health: { compressor_flow_capacity_delta: number; compressor_efficiency_delta: number; turbine_efficiency_delta: number }
  sensors: Partial<Record<SimChannel, SimSensorFault>>
  fuel_valve_lag_s: number | null
}

export interface SimState {
  t_s: number
  step: number
  state: string
  breaker_closed: boolean
  flame: boolean
  trip_cause: string | null
  grid: SimGrid
  speed_pu: number
  speed_hz_equivalent: number
  grid_frequency_hz: number | null
  fsr: number
  limiter: string
  fuel_flow_kg_s: number
  electrical_power_mw: number
  shaft_power_mw: number
  load_setpoint_mw: number
  load_reference_mw: number
  ramp_mw_per_min: number
  exhaust_temperature_k: number
  exhaust_temperature_c: number
  temperature_limit_k: number
  trip_temperature_k: number
  igv_position: number
  igv_mode: 'auto' | 'manual'
  ambient_temperature_c: number
  heat_rate_kj_per_kwh: number | null
  compressor_discharge_temperature_k: number
  compressor_discharge_pressure_kpa: number
  measured: SimMeasured
  injected_faults: SimInjectedFaults
  alarms: SimAlarm[]
  available_commands: string[]
  synthetic_simulation: true
}

export interface SimCreated { session_id: string; config: SimConfig; state: SimState; model_note: string }
export interface SimCommandResult { event: { step: number; command: string; params: Record<string, unknown> }; state: SimState }
export interface SimAdvanceResult { state: SimState; samples: SimState[] }
