import { Fragment, useEffect, useMemo } from 'react'
import { Html, Outlines, useGLTF } from '@react-three/drei'
import { createPortal, useFrame, useThree, type ThreeEvent } from '@react-three/fiber'
import { Box3, Color, Group, Mesh, MeshStandardMaterial, PerspectiveCamera, Sphere, Vector3 } from 'three'
import type { Object3D } from 'three'
import type { CameraFocusTarget, PartInspection, ViewerControls } from './types'
import { EXPLODED_OFFSETS } from './types'
import { componentIdFor, inspectObject, isRotorPart, normalizeComponentId, partIdFor } from './selection'

export function GLBModel({
  url,
  selectedComponentId,
  selectedPart,
  isolated,
  exploded,
  spinning,
  onSelectComponent,
  onInspectPart,
  onPartsAvailable,
  selectedTone,
  stagePart,
  selectedLabel,
  onCameraFocus,
}: {
  url: string
  selectedComponentId: string
  selectedPart: PartInspection | null
  isolated: boolean
  exploded: boolean
  spinning: boolean
  onSelectComponent: (componentId: string) => void
  onInspectPart: (part: PartInspection) => void
  onPartsAvailable: (parts: PartInspection[]) => void
  selectedTone: string
  stagePart: string
  selectedLabel: string
  onCameraFocus: (target: CameraFocusTarget | null) => void
}) {
  const gltf = useGLTF(url)
  const camera = useThree((state) => state.camera)
  const gl = useThree((state) => state.gl)
  const controls = useThree((state) => state.controls as unknown as ViewerControls | null)
  const fittedScene = useMemo(() => {
    const scene = gltf.scene.clone(true)
    scene.traverse((object) => {
      const metadata = object.userData as Record<string, unknown>
      if (typeof metadata.component_id === 'string') {
        object.userData.turbineiqBasePosition = object.position.toArray()
      }
      if (object instanceof Mesh) {
        object.userData.turbineiqComponentId = componentIdFor(object)
        object.material = Array.isArray(object.material)
          ? object.material.map((material) => material.clone())
          : object.material.clone()
        object.castShadow = true
        object.receiveShadow = true
      }
    })
    const wrapper = new Group()
    wrapper.add(scene)
    const bounds = new Box3().setFromObject(wrapper)
    const size = bounds.getSize(new Vector3())
    const center = bounds.getCenter(new Vector3())
    scene.position.sub(center)
    wrapper.scale.setScalar(8.6 / Math.max(size.x, size.y, size.z, 0.001))
    return wrapper
  }, [gltf.scene])
  const rotorParts = useMemo(() => {
    const parts: Object3D[] = []
    fittedScene.traverse((object) => {
      if (isRotorPart(object)) parts.push(object)
    })
    return parts
  }, [fittedScene])
  const partCatalog = useMemo(() => {
    const parts: PartInspection[] = []
    fittedScene.traverse((object) => {
      if (!(object instanceof Mesh)) return
      const componentId = componentIdFor(object)
      if (componentId) parts.push(inspectObject(object, componentId))
    })
    return parts
  }, [fittedScene])
  const selectedMeshes = useMemo(() => {
    const meshes: Mesh[] = []
    fittedScene.traverse((object) => {
      if (!(object instanceof Mesh)) return
      const componentId = componentIdFor(object)
      const selected = selectedPart
        ? partIdFor(object, componentId) === selectedPart.objectId
        : componentId === selectedComponentId
      if (selected) meshes.push(object)
    })
    return meshes
  }, [fittedScene, selectedComponentId, selectedPart])

  useEffect(() => {
    onPartsAvailable(partCatalog)
  }, [onPartsAvailable, partCatalog])

  useEffect(() => {
    fittedScene.traverse((object) => {
      const metadata = object.userData as Record<string, unknown>
      const componentId = normalizeComponentId(metadata.component_id)
      if (componentId) {
        const basePosition = metadata.turbineiqBasePosition
        if (Array.isArray(basePosition) && basePosition.length === 3) {
          object.position.set(Number(basePosition[0]), Number(basePosition[1]), Number(basePosition[2]))
        }
        if (exploded) {
          const offset = EXPLODED_OFFSETS[componentId]
          if (offset) object.position.add(new Vector3(...offset))
        }
      }
      if (!(object instanceof Mesh)) return
      const objectComponentId = componentIdFor(object)
      object.visible = !isolated
        || (selectedPart ? partIdFor(object, objectComponentId) === selectedPart.objectId : objectComponentId === selectedComponentId)
      const materials = Array.isArray(object.material) ? object.material : [object.material]
      materials.forEach((material) => {
        if (material instanceof MeshStandardMaterial) {
          material.color = new Color(stagePart)
          material.emissive = new Color('#000000')
          material.emissiveIntensity = 0
        }
      })
    })
  }, [exploded, fittedScene, isolated, selectedComponentId, selectedPart, selectedTone, stagePart])

  useEffect(() => {
    if (!isolated || !controls) return
    fittedScene.updateMatrixWorld(true)
    const visibleBounds = new Box3()
    fittedScene.traverse((object) => {
      if (object instanceof Mesh && object.visible) visibleBounds.expandByObject(object)
    })
    if (visibleBounds.isEmpty()) return

    const sphere = visibleBounds.getBoundingSphere(new Sphere())
    const direction = camera.position.clone().sub(controls.target)
    if (direction.lengthSq() < 1e-8) direction.set(-6.4, -4.4, 7.6)
    direction.normalize()
    const fov = camera instanceof PerspectiveCamera ? camera.fov : 35
    const distance = Math.max(sphere.radius / Math.sin((fov * Math.PI) / 360) * 1.35, 0.45)
    const position = sphere.center.clone().addScaledVector(direction, distance)
    onCameraFocus({
      position: [position.x, position.y, position.z],
      target: [sphere.center.x, sphere.center.y, sphere.center.z],
    })
  }, [camera, controls, exploded, fittedScene, isolated, onCameraFocus, selectedComponentId, selectedPart])

  useFrame((state, delta) => {
    if (!spinning) return
    const step = Math.min(delta, 0.05) * 4.2
    rotorParts.forEach((object) => { object.rotation.x += step })
    state.invalidate()
  })

  return (
    <>
      <primitive
        object={fittedScene}
        onClick={(event: ThreeEvent<MouseEvent>) => {
          const componentId = componentIdFor(event.object)
          if (componentId) {
            event.stopPropagation()
            onSelectComponent(componentId)
            onInspectPart(inspectObject(event.object, componentId))
          }
        }}
      />
      {selectedMeshes.map((mesh, index) => <Fragment key={`outline-${index}`}>
        {createPortal(<Outlines color={selectedTone} thickness={1.5 * gl.getPixelRatio()} toneMapped={false} />, mesh)}
      </Fragment>)}
      {selectedMeshes[0] && createPortal(
        <Html position={getMeshLabelAnchor(selectedMeshes[0])} center>
          <span className="viewer-selection-label">{selectedPart?.name ?? selectedLabel}</span>
        </Html>,
        selectedMeshes[0],
      )}
    </>
  )
}

function getMeshLabelAnchor(mesh: Mesh): [number, number, number] {
  if (!mesh.geometry.boundingBox) mesh.geometry.computeBoundingBox()
  const bounds = mesh.geometry.boundingBox
  if (!bounds) return [0, 0, 0]
  const center = bounds.getCenter(new Vector3())
  return [center.x, bounds.max.y, center.z]
}

