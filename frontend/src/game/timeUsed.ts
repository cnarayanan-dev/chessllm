// Time used (CONTEXT.md): each side's total time on its moves, as the backend counted it, and the side to move's
// total ticking on from the last state the backend sent. Only the time since that state is the browser's own.
import type { Color, GameState } from '@/api/types'

const two = (n: number) => String(n).padStart(2, '0')

/** A Time used in whole seconds: `Xm SSs` up to `59m 59s`, then `Xh MMm SSs`. */
export function formatTimeUsed(seconds: number): string {
  const whole = Math.floor(seconds)
  const hours = Math.floor(whole / 3600)
  const minutes = Math.floor((whole % 3600) / 60)
  const rest = two(whole % 60)
  return hours > 0 ? `${hours}h ${two(minutes)}m ${rest}s` : `${minutes}m ${rest}s`
}

/**
 * Each side's Time used at `since` (Date.now(), when the state it comes from arrived), the side to move's running move
 * included, and the side whose total ticks on from then, if any. `running_s` is the backend's for that state, to tell
 * from the next poll whether the move still runs.
 */
export type Clock = {
  totals: GameState['time_used']
  ticking: Color | null
  since: number
  running_s: number | null
}

/** A side's Time used at `now` (Date.now()), in seconds, counted in whole milliseconds so it turns on the second. */
export const liveTotal = (clock: Clock, color: Color, now: number): number =>
  (Math.round(clock.totals[color] * 1000) + (clock.ticking === color ? Math.max(0, now - clock.since) : 0)) / 1000

/** `totals` with the side's own replaced. */
const withTotal = (totals: Clock['totals'], color: Color, total: number) => ({ ...totals, [color]: total })

/**
 * The clock of a state that arrived at `at`. The side to move ticks while its move runs: the human's from when their
 * position is ready, an LLM's while its Turn runs or is asked for (`asked`: the page asks for it as the state
 * arrives), from running_s, which is null until the backend starts the Turn. Nobody ticks once the game is over.
 */
export function clockAt(game: GameState, at: number, asked: boolean): Clock {
  const running_s = game.running_s
  if (game.status !== 'playing' || (running_s === null && !asked)) {
    return { totals: game.time_used, ticking: null, since: at, running_s }
  }
  const totals = withTotal(game.time_used, game.turn, game.time_used[game.turn] + (running_s ?? 0))
  return { totals, ticking: game.turn, since: at, running_s }
}

/** The clock standing still at what it showed at `at`: nobody drives the game (a failed request). */
export function stopped(clock: Clock, at: number): Clock {
  const color = clock.ticking
  if (color === null) return clock
  return { ...clock, totals: withTotal(clock.totals, color, liveTotal(clock, color, at)), ticking: null }
}

/**
 * The clock of the LLM to move in `game`, set again from `polled`, the same game as the page polled it at `at` while
 * the LLM's turn request is pending, whose answer only comes once the turn and what follows it are over. The page
 * would otherwise count what the backend doesn't: the time the request and its answer travel, and the Legal
 * counterpart and the evaluation, asked for after the move. The LLM's total stands still once the poll shows its
 * move landed, or once running_s stops advancing between polls (the backend holds it at the Turn's time while the
 * Legal counterpart is asked for), so it jumps back by at most a poll's interval when the answer lands.
 */
export function resynced(clock: Clock, game: GameState, polled: GameState, at: number): Clock {
  const color = game.turn
  if (polled.llm_turns.length > game.llm_turns.length || polled.turn !== color || polled.status !== 'playing') {
    return { ...clock, totals: withTotal(clock.totals, color, polled.time_used[color]), ticking: null }
  }
  const running_s = polled.running_s
  if (running_s === null) return clock
  const totals = withTotal(clock.totals, color, polled.time_used[color] + running_s)
  const advancing = clock.running_s === null || running_s > clock.running_s
  return { totals, ticking: advancing ? color : null, since: at, running_s }
}
