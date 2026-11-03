import type {
  AssistantResponse,
  EvidenceResponse,
  ScenarioDefinition,
  SelectedTwinSelection,
  TwinRunPayload,
} from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail = typeof body?.detail === 'string' ? body.detail : `Request failed (${response.status})`
    throw new Error(detail)
  }
  return (await response.json()) as T
}

export const api = {
  health: () => request<{ status: string; synthetic_only: boolean; industrial_connection: boolean }>(
    '/api/health',
  ),
  scenarios: () => request<ScenarioDefinition[]>('/api/scenarios'),
  run: (scenarioId: string, seed: number) =>
    request<TwinRunPayload>(
      `/api/twin/run?scenario_id=${encodeURIComponent(scenarioId)}&seed=${seed}&samples=96&sample_index=48`,
    ),
  evidence: (query: string) =>
    request<EvidenceResponse>(`/api/evidence/search?q=${encodeURIComponent(query)}&top_k=4`),
  ask: (
    question: string,
    enableCloud: boolean,
    allowCloudDocumentContext: boolean,
    selectedTwin: SelectedTwinSelection | null,
  ) =>
    request<AssistantResponse>('/api/assistant/ask', {
      method: 'POST',
      body: JSON.stringify({
        question,
        enable_cloud: enableCloud,
        allow_cloud_document_context: allowCloudDocumentContext,
        selected_twin: selectedTwin,
      }),
    }),
}
