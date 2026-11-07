import type { ComponentId } from '../../app/router'
import type { TimelinePoint, TwinSnapshot } from '../../types'
import { celsiusToKelvin, fixedNumber } from '../../lib/format'
import { ValueWithUnit } from '../../lib/ValueWithUnit'
import './StationLedger.css'

const STATIONS: Array<{ number: number; name: string; component: ComponentId }> = [
  { number: 1, name: 'Inlet', component: 'inlet' },
  { number: 2, name: 'Compressor discharge', component: 'compressor' },
  { number: 3, name: 'Turbine inlet', component: 'combustor' },
  { number: 4, name: 'Exhaust', component: 'turbine' },
]

function stationTemperature(snapshot: TwinSnapshot, row: TimelinePoint | undefined, station: number): { synthetic: number | null; reference: number | null; unit: string } {
  if (station === 1) return { synthetic: celsiusToKelvin(snapshot.ambient_temperature_c), reference: null, unit: 'K' }
  if (station === 2) return { synthetic: snapshot.compressor_discharge_temperature_k, reference: snapshot.reference_compressor_discharge_temperature_k, unit: 'K' }
  if (station === 3) {
    const reference = row?.reference_turbine_inlet_temperature_k
    return { synthetic: snapshot.turbine_inlet_temperature_k, reference: typeof reference === 'number' ? reference : null, unit: 'K' }
  }
  return { synthetic: snapshot.exhaust_temperature_k, reference: snapshot.reference_exhaust_temperature_k, unit: 'K' }
}

export function StationLedger({ snapshot, timelineRow, selectedComponentId, hoveredComponent, onSelect, onHover }: { snapshot: TwinSnapshot; timelineRow?: TimelinePoint; selectedComponentId: ComponentId; hoveredComponent: ComponentId | null; onSelect: (id: ComponentId) => void; onHover: (id: ComponentId | null) => void }) {
  return (
    <section className="station-ledger panel" aria-labelledby="station-ledger-title">
      <div className="card-heading"><h2 id="station-ledger-title">Station ledger</h2><span>Temperature · K</span></div>
      <div className="station-list">
        <div className="station-header" aria-hidden="true"><span /><span>Synthetic</span><span>Reference model</span><span>Note</span></div>
        {STATIONS.map((station) => {
          const values = stationTemperature(snapshot, timelineRow, station.number)
          const active = (hoveredComponent ?? selectedComponentId) === station.component
          const note = station.number === 1 ? `${fixedNumber(snapshot.ambient_pressure_kpa, 1)} kPa ambient pressure · source ${fixedNumber(snapshot.ambient_temperature_c, 1)} °C` : ''
          return (
            <button key={station.number} type="button" className={`station-row ${active ? 'is-selected' : ''}`} onMouseEnter={() => onHover(station.component)} onMouseLeave={() => onHover(null)} onFocus={() => onHover(station.component)} onBlur={() => onHover(null)} onClick={() => onSelect(station.component)}>
              <span className="station-name"><span className="station-number">{station.number}</span><span>{station.name}</span></span>
              <span className="station-observed"><ValueWithUnit value={values.synthetic === null ? '—' : fixedNumber(values.synthetic, 1)} unit={values.unit} /></span>
              <span className="station-reference"><ValueWithUnit value={values.reference === null ? '—' : fixedNumber(values.reference, 1)} unit={values.unit} /></span>
              <span className="station-note">{note}</span>
            </button>
          )
        })}
      </div>
    </section>
  )
}
