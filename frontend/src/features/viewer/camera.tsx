import { useEffect, useRef, useState } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import { Vector3 } from 'three'
import type { CameraFocusTarget, ViewerControls } from './types'

interface CameraTransition {
  startPosition: Vector3
  endPosition: Vector3
  startTarget: Vector3
  endTarget: Vector3
  elapsedMs: number
  durationMs: number
}

function transitionDuration(): number {
  const value = getComputedStyle(document.documentElement).getPropertyValue('--dur-slow').trim()
  const amount = Number.parseFloat(value)
  if (!Number.isFinite(amount)) return 240
  return value.endsWith('s') && !value.endsWith('ms') ? amount * 1000 : amount
}

export function ViewerCameraController({ resetKey, focusTarget }: { resetKey: number; focusTarget: CameraFocusTarget | null }) {
  const { camera, controls, invalidate } = useThree((state) => ({
    camera: state.camera,
    controls: state.controls as unknown as ViewerControls | null,
    invalidate: state.invalidate,
  }))
  const [reduceMotion, setReduceMotion] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  const transitionRef = useRef<CameraTransition | null>(null)
  const previousResetKey = useRef(resetKey)

  useEffect(() => {
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setReduceMotion(preference.matches)
    preference.addEventListener('change', update)
    update()
    return () => preference.removeEventListener('change', update)
  }, [])

  useEffect(() => {
    if (!controls) return
    const resetRequested = resetKey !== previousResetKey.current
    previousResetKey.current = resetKey
    const destinationPosition = resetRequested
      ? new Vector3(-6.4, -4.4, 7.6)
      : focusTarget ? new Vector3(...focusTarget.position) : null
    const destinationTarget = resetRequested
      ? new Vector3(0, 0, 0)
      : focusTarget ? new Vector3(...focusTarget.target) : null
    if (!destinationPosition || !destinationTarget) return

    const startPosition = camera.position.clone()
    const startTarget = controls.target.clone()
    if (reduceMotion) {
      camera.position.copy(destinationPosition)
      controls.target.copy(destinationTarget)
      controls.update()
      transitionRef.current = null
      invalidate()
      return
    }

    transitionRef.current = {
      startPosition,
      endPosition: destinationPosition,
      startTarget,
      endTarget: destinationTarget,
      elapsedMs: 0,
      durationMs: transitionDuration(),
    }
    invalidate()
  }, [camera, controls, focusTarget, invalidate, reduceMotion, resetKey])

  useEffect(() => {
    const transition = transitionRef.current
    if (!reduceMotion || !transition || !controls) return
    camera.position.copy(transition.endPosition)
    controls.target.copy(transition.endTarget)
    controls.update()
    transitionRef.current = null
    invalidate()
  }, [camera, controls, invalidate, reduceMotion])

  useFrame((_, delta) => {
    const transition = transitionRef.current
    if (!transition || !controls) return
    transition.elapsedMs = Math.min(transition.durationMs, transition.elapsedMs + Math.min(delta, 1 / 30) * 1000)
    const progress = transition.durationMs === 0 ? 1 : transition.elapsedMs / transition.durationMs
    const eased = 1 - (1 - progress) ** 3
    camera.position.lerpVectors(transition.startPosition, transition.endPosition, eased)
    controls.target.lerpVectors(transition.startTarget, transition.endTarget, eased)
    controls.update()
    if (progress >= 1) transitionRef.current = null
    else invalidate()
  })

  return null
}
