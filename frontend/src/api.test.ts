import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'

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
    const result = await api.streamAssistant('Explain the cycle.', false, false, null, (name) => events.push(name), new AbortController().signal)
    expect(result.answer).toBe('Grounded answer.')
    expect(events).toEqual(['status', 'tool_start', 'token', 'token', 'done'])
  })
})
