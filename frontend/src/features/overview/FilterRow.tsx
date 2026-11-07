import { useTurbineStore } from '../../app/useTurbineStore'
import type { TwinSnapshot } from '../../types'
import { formatUtcTime } from '../../lib/format'
import './FilterRow.css'

export function FilterRow({ sample, stopPlayback }: { sample: TwinSnapshot | null; stopPlayback: () => void }) {
  const { state, changeScenario, dispatch, commitSeed } = useTurbineStore()
  const parsedSeed = /^\d+$/.test(state.seedInput) && Number.isSafeInteger(Number(state.seedInput))
  const selected = sample ?? state.run?.snapshots[state.sampleIndex] ?? null
  const sampleCount = state.run?.run.sample_count ?? 96
  const time = selected ? formatUtcTime(selected.timestamp_utc) : '--:--'
  const commit = () => { if (parsedSeed && Number(state.seedInput) !== state.seed) { stopPlayback(); commitSeed(state.seedInput) } }
  return (
    <form className="filter-row" aria-label="Synthetic run filters" onSubmit={(event) => { event.preventDefault(); commit() }}>
      <label className="filter-group filter-scenario">
        <span className="filter-label">Scenario</span>
        <select aria-label="Scenario" value={state.scenarioId} onChange={(event) => { stopPlayback(); changeScenario(event.target.value) }}>
          {state.scenarios.map((scenario) => <option key={scenario.scenario_id} value={scenario.scenario_id}>{scenario.name}</option>)}
          {state.scenarios.length === 0 && <option value={state.scenarioId}>{state.run?.run.scenario_name ?? state.scenarioId}</option>}
        </select>
      </label>
      <label className={`filter-group filter-seed ${!parsedSeed ? 'has-error' : ''}`}>
        <span className="filter-label">Seed</span>
        <input aria-label="Seed" aria-invalid={!parsedSeed} value={state.seedInput} inputMode="numeric" onChange={(event) => dispatch({ type: 'seed-draft', value: event.target.value })} onBlur={commit} />
        {!parsedSeed && <span className="filter-error" role="alert">Enter a non-negative whole number.</span>}
      </label>
      <div className="filter-group filter-sample" aria-label="Selected sample">
        <span className="filter-label">Sample</span>
        <span className="filter-value">{state.sampleIndex + 1} of {sampleCount} · {time} UTC</span>
      </div>
      <div className="filter-group filter-interval">
        <span className="filter-label">Interval</span>
        <span className="filter-value">{state.run?.run.sample_interval_minutes ?? 15} min</span>
      </div>
      {state.loading && state.run && <span className="filter-status" role="status">Updating run; previous sample remains visible.</span>}
    </form>
  )
}
