import type { ReactNode } from 'react'

export function ValueWithUnit({ value, unit, className = '' }: { value: ReactNode; unit?: string; className?: string }) {
  return <span className={className}>{value}{unit && <span className="unit">{unit}</span>}</span>
}
