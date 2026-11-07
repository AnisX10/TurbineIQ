import { describe, expect, it } from 'vitest'
import { BoxGeometry, Group, Mesh, MeshBasicMaterial } from 'three'
import { componentIdFor, inspectObject, isRotorPart, normalizeComponentId, partIdFor } from './selection'

describe('viewer selection mapping', () => {
  it('normalizes the six public component IDs and their existing aliases', () => {
    expect(['inlet', 'intake', 'air_entry'].map(normalizeComponentId)).toEqual(['inlet', 'inlet', 'inlet'])
    expect(['compressor', 'comp_stage', 'compressor_casing'].map(normalizeComponentId)).toEqual(['compressor', 'compressor', 'compressor'])
    expect(['combustor', 'combustion', 'combustion_chamber'].map(normalizeComponentId)).toEqual(['combustor', 'combustor', 'combustor'])
    expect(['turbine', 'turbine_stage', 'turbine_casing'].map(normalizeComponentId)).toEqual(['turbine', 'turbine', 'turbine'])
    expect(['shaft', 'rotor', 'spool'].map(normalizeComponentId)).toEqual(['shaft', 'shaft', 'shaft'])
    expect(['generator', 'alternator'].map(normalizeComponentId)).toEqual(['generator', 'generator'])
    expect(normalizeComponentId('unknown')).toBeNull()
  })

  it('resolves component IDs from mesh metadata, names, and parent aliases', () => {
    const metadataMesh = new Mesh(new BoxGeometry(), new MeshBasicMaterial())
    metadataMesh.userData.component_id = 'air_entry'
    expect(componentIdFor(metadataMesh)).toBe('inlet')

    const namedMesh = new Mesh(new BoxGeometry(), new MeshBasicMaterial())
    namedMesh.name = 'compressor_casing'
    expect(componentIdFor(namedMesh)).toBe('compressor')

    const parent = new Group()
    parent.name = 'combustion chamber assembly'
    const child = new Mesh(new BoxGeometry(), new MeshBasicMaterial())
    parent.add(child)
    expect(componentIdFor(child)).toBe('combustor')
    expect(componentIdFor(new Group())).toBeNull()
  })

  it('keeps the existing mesh ID and inspection metadata mapping', () => {
    const mesh = new Mesh(new BoxGeometry(), new MeshBasicMaterial())
    mesh.name = 'Stage_1 | Rotating_Buckets'
    mesh.userData = {
      row_role: 'rotor stage',
      public_component_envelope_mm: '120 x 90',
      public_component_mass_kg: 14.2,
      public_reference_label: 'Published 6B.03 reference',
      row_instance_index: 1,
      row_instance_count: 4,
    }

    expect(partIdFor(mesh, 'turbine')).toBe('turbine:Stage_1 | Rotating_Buckets')
    expect(inspectObject(mesh, 'turbine')).toMatchObject({
      componentId: 'turbine',
      objectId: 'turbine:Stage_1 | Rotating_Buckets',
      name: 'Stage 1 · Rotating Buckets',
      role: 'rotor stage',
      envelopeMm: '120 x 90',
      massKg: 14.2,
      referenceLabel: 'Published 6B.03 reference',
      instanceIndex: 1,
      instanceCount: 4,
    })
  })

  it('identifies only the existing rotor mesh name patterns', () => {
    const rotor = new Group()
    rotor.name = 'Stage 1 Rotating Buckets'
    const shaft = new Group()
    shaft.name = 'Main Rotor Shaft'
    const casing = new Group()
    casing.name = 'Compressor casing'

    expect(isRotorPart(rotor)).toBe(true)
    expect(isRotorPart(shaft)).toBe(true)
    expect(isRotorPart(casing)).toBe(false)
  })
})
