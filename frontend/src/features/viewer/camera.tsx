import { useEffect } from 'react'
import { useThree } from '@react-three/fiber'
import type { ViewerControls } from './types'

export function ViewerCameraReset({ resetKey }: { resetKey: number }) {
  const controls = useThree((state) => state.controls as unknown as ViewerControls | null)
  useEffect(() => {
    if (resetKey > 0) controls?.reset()
  }, [controls, resetKey])
  return null
}

