import type {
  AssistantResponse,
  EvidenceResponse,
  ScenarioDefinition,
  SelectedTwinSelection,
  TwinRunPayload,
} from './types'

export interface AssistantProviderStatus {
  provider: string
  model: string
  base_url_host: string
  configured: boolean
}

export interface AssistantStreamEvent {
  status?: { state: string; message: string }
  tool_start?: { name: string; arguments?: Record<string, unknown> }
  tool_result?: { name: string }
  token?: { text: string }
  done?: AssistantResponse
  error?: { message: string }
}

export class ConsentRequiredError extends Error {
  code: string

  constructor(code: string, message: string) {
    super(message)
    this.name = 'ConsentRequiredError'
    this.code = code
  }
}

export interface ConsentGrant {
  consent_token: string
  expires_in_seconds: number
  provider: string
  model: string
  base_url_host: string
  include_documents: boolean
}

function failureFrom(status: number, body: unknown, fallback: string): Error {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return new Error(detail)
  if (detail && typeof detail === 'object') {
    const { code, message } = detail as { code?: unknown; message?: unknown }
    const text = typeof message === 'string' ? message : fallback
    if (status === 403 && typeof code === 'string' && code.includes('consent')) {
      return new ConsentRequiredError(code, text)
    }
    return new Error(text)
  }
  return new Error(fallback)
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw failureFrom(response.status, body, `Request failed (${response.status})`)
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
  evidence: (query: string, topK = 4) =>
    request<EvidenceResponse>(`/api/evidence/search?q=${encodeURIComponent(query)}&top_k=${topK}`),
  assistantStatus: () => request<AssistantProviderStatus>('/api/assistant/status'),
  testAssistantProvider: () => request<{
    provider: string
    model: string
    configured: boolean
    tools_work: boolean
    latency_ms: number | null
    message: string
  }>('/api/assistant/test', { method: 'POST', body: '{}' }),
  grantConsent: (includeDocuments: boolean) =>
    request<ConsentGrant>('/api/assistant/consent', {
      method: 'POST',
      body: JSON.stringify({ include_documents: includeDocuments }),
    }),
  revokeConsent: (consentToken: string) =>
    request<{ revoked: boolean }>('/api/assistant/consent/revoke', {
      method: 'POST',
      body: JSON.stringify({ consent_token: consentToken }),
    }),
  ask: (
    question: string,
    enableCloud: boolean,
    allowCloudDocumentContext: boolean,
    selectedTwin: SelectedTwinSelection | null,
    consentToken: string | null = null,
  ) =>
    request<AssistantResponse>('/api/assistant/ask', {
      method: 'POST',
      body: JSON.stringify({
        question,
        enable_cloud: enableCloud,
        allow_cloud_document_context: allowCloudDocumentContext,
        selected_twin: selectedTwin,
        consent_token: consentToken,
      }),
    }),
  streamAssistant: async (
    question: string,
    enableCloud: boolean,
    allowCloudDocumentContext: boolean,
    selectedTwin: SelectedTwinSelection | null,
    consentToken: string | null,
    onEvent: (name: keyof AssistantStreamEvent, payload: AssistantStreamEvent[keyof AssistantStreamEvent]) => void,
    signal: AbortSignal,
  ): Promise<AssistantResponse> => {
    const response = await fetch('/api/assistant/stream', {
      method: 'POST',
      signal,
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify({
        question,
        enable_cloud: enableCloud,
        allow_cloud_document_context: allowCloudDocumentContext,
        selected_twin: selectedTwin,
        consent_token: consentToken,
      }),
    })
    if (!response.ok && [404, 405, 415, 501].includes(response.status)) {
      return api.ask(question, enableCloud, allowCloudDocumentContext, selectedTwin, consentToken)
    }
    if (!response.ok) {
      const body = await response.json().catch(() => null)
      throw failureFrom(response.status, body, `Assistant request failed (${response.status})`)
    }
    if (!response.headers.get('content-type')?.includes('text/event-stream') || !response.body) {
      return api.ask(question, enableCloud, allowCloudDocumentContext, selectedTwin, consentToken)
    }
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let finalResponse: AssistantResponse | null = null
    const dispatchEvents = (chunk: string) => {
      buffer += chunk
      const events = buffer.split(/\r?\n\r?\n/)
      buffer = events.pop() ?? ''
      for (const block of events) {
        let eventName = ''
        const data: string[] = []
        for (const line of block.split(/\r?\n/)) {
          if (line.startsWith('event:')) eventName = line.slice(6).trim()
          else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
        }
        if (!eventName || !data.length) continue
        const payload = JSON.parse(data.join('\n')) as AssistantStreamEvent[keyof AssistantStreamEvent]
        onEvent(eventName as keyof AssistantStreamEvent, payload)
        if (eventName === 'error') {
          throw new Error((payload as AssistantStreamEvent['error'])?.message ?? 'Assistant request failed.')
        }
        if (eventName === 'done') finalResponse = payload as AssistantResponse
      }
    }
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      dispatchEvents(decoder.decode(value, { stream: true }))
    }
    dispatchEvents(decoder.decode())
    if (!finalResponse) throw new Error('The assistant stream ended before the answer was complete.')
    return finalResponse
  },
}
