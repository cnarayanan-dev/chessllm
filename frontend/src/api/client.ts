// The game endpoints, typed with the generated API types.
import type {
  GameState,
  NewGame,
  NewPromptTemplate,
  Probe,
  ProbeRequest,
  PromptTemplateInfo,
  Ranking,
  TurnPrompt,
} from '@/api/types'

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

/** Saves a new Prompt template in the library, with a new ID; refused (400), saying why, if its side couldn't play it. */
export const savePromptTemplate = (template: NewPromptTemplate, signal?: AbortSignal) =>
  api<PromptTemplateInfo>('POST', '/api/prompt-templates', template, signal)

/** Leaves a saved Prompt template out of the library's list, and answers the list as it is now. */
export const hidePromptTemplate = (templateId: string, signal?: AbortSignal) =>
  api<PromptTemplateInfo[]>('POST', `/api/prompt-templates/${encodeURIComponent(templateId)}/hide`, undefined, signal)

/** Starts a game with these settings, or the backend's default settings with null. */
export const startGame = (newGame: NewGame | null, signal?: AbortSignal) =>
  api<GameState>('POST', '/api/games', newGame ?? undefined, signal)

export const playMove = (uci: string, signal?: AbortSignal) =>
  api<GameState>('POST', '/api/games/current/moves', { uci }, signal)

export const playLlmTurn = (signal?: AbortSignal) =>
  api<GameState>('POST', '/api/games/current/llm-turn', undefined, signal)

/**
 * The whole Prompt of an attempt (numbered from 1) of the current game's LLM turn at `ply`, by turn, rebuilt by the API
 * from the records: in a conversation the state holds only what each attempt added (ADR 0009).
 */
export const getTurnPrompt = (ply: number, attempt: number, signal?: AbortSignal) =>
  api<TurnPrompt>('GET', `/api/games/current/llm-turns/${ply}/attempts/${attempt}/prompt`, undefined, signal)

/** Asks a Probe about a past LLM turn of the current game; refused (409) while an LLM turn runs. */
export const askProbe = (request: ProbeRequest, signal?: AbortSignal) =>
  api<Probe>('POST', '/api/games/current/probes', request, signal)

/** A game's Probes, in the order they were asked, from its probe log. */
export const getProbes = (gameId: string, signal?: AbortSignal) =>
  api<Probe[]>('GET', `/api/games/${gameId}/probes`, undefined, signal)

/** The Ranking, from the games of the Modes its path names (rankingPath). */
export const getRanking = (path: string, signal?: AbortSignal) => api<Ranking>('GET', path, undefined, signal)
