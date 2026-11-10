export interface AssistantSuggestionContext {
  flaggedSamples: number
  sampleNumber: number
  componentName: string
  residualKw: number | null
}

export function generateAssistantSuggestions(context: AssistantSuggestionContext): string[] {
  const screeningQuestion = context.flaggedSamples > 0
    ? `What distinguishes the ${context.flaggedSamples} flagged samples in this run?`
    : `Why was sample ${context.sampleNumber} not flagged by the local residual screen?`
  const componentQuestion = `Explain the ${context.componentName} metrics at sample ${context.sampleNumber}.`
  const residual = context.residualKw === null
    ? 'How should I interpret the current sample residual?'
    : `What does the ${context.residualKw > 0 ? '+' : ''}${context.residualKw.toFixed(1)} kW residual mean?`
  return [screeningQuestion, componentQuestion, residual]
}
