import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ConsentRequiredError } from './api'

afterEach(() => vi.unstubAllGlobals())

describe('assistant SSE client', () => {
  it('parses split event chunks, reports progress, and returns the final response', async () => {
    const chunks = [
      'event: status\ndata: {"state":"working","message":"Preparing"}\n\n',
      'event: tool_start\ndata: {"name":"calculate_cycle"}\n\n',
      'event: token\ndata: {"text":"Grounded "}\n\n',
      'event: token\ndata: {"text":"answer."}\n\n',
      'event: done\ndata: {"answer":"Grounded answer.","mode":"local","warning":null,"tool_calls":[],"synthetic_only":true}\n\n',
    ]
    vi.stubGlobal('fetch', vi.fn(async () => new Response(new ReadableStream<Uint8Array>({
      start(controller) {
        const encoder = new TextEncoder()
        for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
        controller.close()
      },
    }), { headers: { 'Content-Type': 'text/event-stream' } })))
    const events: string[] = []
    const result = await api.streamAssistant('Explain the cycle.', false, false, null, null, (name) => events.push(name), new AbortController().signal)
    expect(result.answer).toBe('Grounded answer.')
    expect(events).toEqual(['status', 'tool_start', 'token', 'token', 'done'])
  })

  it('sends the consent token and raises ConsentRequiredError when the server refuses Cloud', async () => {
    const fetchMock = vi.fn(async () => new Response(
      JSON.stringify({ detail: { code: 'consent_required', message: 'Cloud mode needs your confirmation.' } }),
      { status: 403, headers: { 'Content-Type': 'application/json' } },
    ))
    vi.stubGlobal('fetch', fetchMock)
    const attempt = api.streamAssistant('Explain the cycle.', true, false, null, 'token-123', () => {}, new AbortController().signal)
    await expect(attempt).rejects.toBeInstanceOf(ConsentRequiredError)
    const body = JSON.parse((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body as string)
    expect(body.consent_token).toBe('token-123')
    expect(body.enable_cloud).toBe(true)
  })

  it('keeps plain string errors as ordinary errors', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(
      JSON.stringify({ detail: 'Assistant request limit reached.' }),
      { status: 429, headers: { 'Content-Type': 'application/json' } },
    )))
    const attempt = api.streamAssistant('Explain the cycle.', false, false, null, null, () => {}, new AbortController().signal)
    await expect(attempt).rejects.toThrow('Assistant request limit reached.')
    await expect(attempt).rejects.not.toBeInstanceOf(ConsentRequiredError)
  })
})
