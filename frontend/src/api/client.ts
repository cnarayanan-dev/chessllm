// The game endpoints, typed with the generated API types.
import type { GameState, NewGame, Probe, ProbeRequest, PromptTemplateInfo } from '@/api/types'

/** A response other than 2xx, with the backend's detail as its message. */
export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function api<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  })
  if (!response.ok) {
    const detail = await response.json().then(
      (json: { detail?: unknown }) => json.detail,
      () => undefined,
    )
    throw new ApiError(typeof detail === 'string' ? detail : response.statusText, response.status)
  }
  return response.json() as Promise<T>
}

export const getGame = (signal?: AbortSignal) => api<GameState>('GET', '/api/games/current', undefined, signal)

/** The settings a new game takes by default: the New game sheet starts from them when there is no game. */
export const getNewGameDefaults = (signal?: AbortSignal) => api<NewGame>('GET', '/api/games/defaults', undefined, signal)

/** The Prompt library's templates that aren't hidden, the defaults first. */
export const getPromptTemplates = (signal?: AbortSignal) =>
  api<PromptTemplateInfo[]>('GET', '/api/prompt-templates', undefined, signal)

/** Starts a game with these settings, or the backend's default settings with null. */
export const startGame = (newGame: NewGame | null, signal?: AbortSignal) =>
  api<GameState>('POST', '/api/games', newGame ?? undefined, signal)

export const playMove = (uci: string, signal?: AbortSignal) =>
  api<GameState>('POST', '/api/games/current/moves', { uci }, signal)

export const playLlmTurn = (signal?: AbortSignal) =>
  api<GameState>('POST', '/api/games/current/llm-turn', undefined, signal)

/** Probes a past LLM turn of the current game; refused (409) while an LLM turn runs. */
export const probeTurn = (request: ProbeRequest, signal?: AbortSignal) =>
  api<Probe>('POST', '/api/games/current/probes', request, signal)

/** Every probe of the game, in the order asked, from its probe log. */
export const getProbes = (gameId: string, signal?: AbortSignal) =>
  api<Probe[]>('GET', `/api/games/${gameId}/probes`, undefined, signal)
