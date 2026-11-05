import type { StageTokens } from './stageTokens'

export function StageLights({ tokens }: { tokens: StageTokens }) {
  return <>
    <ambientLight intensity={tokens.ambient} />
    <directionalLight position={[4, 8, 5]} intensity={tokens.keyLight} color="#dce8ed" />
    <pointLight position={[-2.5, 1.2, 2.5]} intensity={tokens.fillLight} distance={10} color="#a9c6c8" />
    <pointLight position={[1.4, 0.8, -2]} intensity={tokens.rimLight} distance={8} color="#d5d9da" />
  </>
}
