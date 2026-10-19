// Stands in for the FastAPI backend in tests: each route answers with the responses queued for it, in order, and
// every request is recorded. A response can be held back with `later()` to play out a slow LLM turn.
import { vi } from 'vitest'

type Reply = Response | Error | Promise<Response>

export type Sent = { method: string; path: string; body: unknown }

export function later() {
  let resolve!: (response: Response) => void
  let reject!: (error: Error) => void
  const promise = new Promise<Response>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

export function fakeBackend() {
  const queues = new Map<string, Reply[]>()
  const sent: Sent[] = []

  const fetch = vi.fn(async (path: string, init: RequestInit = {}) => {
    const method = init.method ?? 'GET'
    const body = typeof init.body === 'string' ? JSON.parse(init.body) : init.body
    sent.push({ method, path, body })
    const reply = queues.get(`${method} ${path}`)?.shift()
    if (!reply) return Response.json({ detail: `no reply scripted for ${method} ${path}` }, { status: 500 })
    if (reply instanceof Error) throw reply
    const response = await reply
    if (init.signal?.aborted) throw new DOMException('The operation was aborted.', 'AbortError')
    return response
  })
  vi.stubGlobal('fetch', fetch)

  return {
    sent,
    /** Queues the replies to `METHOD /path`. */
    on(route: string, ...replies: Reply[]) {
      queues.set(route, [...(queues.get(route) ?? []), ...replies])
      return this
    },
    /** The requests sent to `METHOD /path`. */
    sentTo(route: string): Sent[] {
      return sent.filter((request) => `${request.method} ${request.path}` === route)
    },
  }
}
