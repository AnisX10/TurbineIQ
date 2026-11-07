import type { Object3D } from 'three'
import type { PartInspection } from './types'

export const COMPONENT_ALIASES: Record<string, string[]> = {
  inlet: ['inlet', 'intake', 'air_entry'],
  compressor: ['compressor', 'comp_stage', 'compressor_casing'],
  combustor: ['combustor', 'combustion', 'combustion_chamber'],
  turbine: ['turbine', 'turbine_stage', 'turbine_casing'],
  shaft: ['shaft', 'rotor', 'spool'],
  generator: ['generator', 'alternator'],
}

export function normalizeComponentId(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const normalized = value.toLowerCase().replaceAll(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')
  for (const [componentId, aliases] of Object.entries(COMPONENT_ALIASES)) {
    if (componentId === normalized || aliases.includes(normalized)) return componentId
  }
  return null
}

export function inspectObject(object: Object3D, componentId: string): PartInspection {
  const metadata = object.userData as Record<string, unknown>
  const name = object.name || 'Unnamed model part'
  return {
    componentId,
    objectId: `${componentId}:${name}`,
    name: name.replaceAll('_', ' ').replaceAll(/\s*\|\s*/g, ' · ').replaceAll(/\s+/g, ' ').trim(),
    role: typeof metadata.row_role === 'string' ? metadata.row_role : undefined,
    envelopeMm: typeof metadata.public_component_envelope_mm === 'string'
      ? metadata.public_component_envelope_mm
      : undefined,
    massKg: typeof metadata.public_component_mass_kg === 'number'
      ? metadata.public_component_mass_kg
      : undefined,
    referenceLabel: typeof metadata.public_reference_label === 'string'
      ? metadata.public_reference_label
      : undefined,
    referenceEnvelopeMm: typeof metadata.public_reference_envelope_mm === 'string'
      ? metadata.public_reference_envelope_mm
      : undefined,
    referenceMassKg: typeof metadata.public_reference_mass_kg === 'number'
      ? metadata.public_reference_mass_kg
      : undefined,
    dataNote: typeof metadata.envelope_note === 'string'
      ? metadata.envelope_note
      : typeof metadata.reference_note === 'string'
        ? metadata.reference_note
        : undefined,
    source: typeof metadata.envelope_source === 'string'
      ? metadata.envelope_source
      : typeof metadata.reference_source === 'string'
        ? metadata.reference_source
        : undefined,
    geometryNote: typeof metadata.geometry_accuracy === 'string' ? metadata.geometry_accuracy : undefined,
    instanceIndex: typeof metadata.row_instance_index === 'number' ? metadata.row_instance_index : undefined,
    instanceCount: typeof metadata.row_instance_count === 'number' ? metadata.row_instance_count : undefined,
    instanceCountNote: typeof metadata.row_instance_count_note === 'string'
      ? metadata.row_instance_count_note
      : undefined,
  }
}

export function partIdFor(object: Object3D, componentId: string | null): string | null {
  return componentId ? `${componentId}:${object.name || object.uuid}` : null
}

export function normalizedObjectName(name: string): string {
  return name.toLowerCase().replaceAll(/[^a-z0-9]+/g, ' ').replaceAll(/\s+/g, ' ').trim()
}

export function isRotorPart(object: Object3D): boolean {
  const name = normalizedObjectName(object.name)
  return name === 'main rotor shaft'
    || name.startsWith('compressor rotor stage')
    || name.startsWith('compressor rotor disk rim')
    || (name.startsWith('stage ')
      && (name.includes('bucket casting proxy')
        || name.includes('rotating buckets')
        || name.includes('rotor wheel')))
}

export function componentIdFor(object: Object3D): string | null {
  let current: Object3D | null = object
  while (current) {
    const metadata = current.userData as Record<string, unknown>
    const customId = normalizeComponentId(metadata.component_id ?? metadata.componentId)
    if (customId) return customId
    const byName = normalizeComponentId(current.name)
    if (byName) return byName
    for (const [componentId, aliases] of Object.entries(COMPONENT_ALIASES)) {
      if (aliases.some((alias) => current?.name.toLowerCase().includes(alias))) return componentId
    }
    current = current.parent
  }
  return null
}

