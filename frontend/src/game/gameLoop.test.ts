import { describe, expect, test } from 'vitest'
import type { GameState, NewGame } from '@/api/types'
import {
  boardInput,
  gameLoop,
  initialGameLoop,
  phase,
  shownPosition,
  type GameLoop,
  type GameLoopAction,
} from '@/game/gameLoop'
import {
  AFTER_E4,
  AFTER_E5,
  AFTER_NC6,
  AFTER_NF3,
  E4,
  E5,
  NC6,
  NF3,
  START,
  aGame,
  aTurn,
  afterE4,
  afterE5,
  plies,
} from '@/test/games'

function run(...actions: GameLoopAction[]): GameLoop {
  return actions.reduce(gameLoop, initialGameLoop)
}

/** Answers the request now in flight. */
function received(state: GameLoop, game: ReturnType<typeof aGame>): GameLoopAction {
  return { type: 'received', requestId: state.request!.id, game }
}

describe('opening the page', () => {
  test('starts idle, loading the current game', () => {
    expect(phase(initialGameLoop)).toBe('idle')
    expect(initialGameLoop.request).toMatchObject({ kind: 'load' })
    expect(initialGameLoop.game).toBeNull()
  })

  test('shows the loaded game with the human to move', () => {
    const state = run(received(initialGameLoop, aGame()))

    expect(phase(state)).toBe('human')
    expect(state.game).toEqual(aGame())
    expect(state.request).toBeNull()
  })

  test('starts the LLM turn of a loaded game in which the LLM is to move', () => {
    const state = run(received(initialGameLoop, afterE4()))

    expect(phase(state)).toBe('llm')
    expect(state.request).toMatchObject({ kind: 'llm-turn' })
  })
})

describe('the human moves', () => {
  const humanToMove = run(received(initialGameLoop, aGame()))

  test('sends the move, keeping the position until the backend answers', () => {
    const state = gameLoop(humanToMove, { type: 'human-move', uci: 'e2e4' })

    expect(state.request).toMatchObject({ kind: 'move', uci: 'e2e4' })
    expect(state.game).toBe(humanToMove.game)
  })

  test('an accepted move lands at once, with its sound, and the LLM turn follows', () => {
    const sent = gameLoop(humanToMove, { type: 'human-move', uci: 'e2e4' })
    const state = gameLoop(sent, received(sent, afterE4()))

    expect(state.game).toEqual(afterE4())
    expect(state.moveSounds).toBe(humanToMove.moveSounds + 1)
    expect(phase(state)).toBe('llm')
    expect(state.request).toMatchObject({ kind: 'llm-turn' })
    expect(state.request!.id).not.toBe(sent.request!.id)
  })

  test('a move that ends the game starts no LLM turn', () => {
    const sent = gameLoop(humanToMove, { type: 'human-move', uci: 'e2e4' })
    const state = gameLoop(sent, received(sent, afterE4({ status: 'over', result: '1-0', end_reason: 'checkmate' })))

    expect(phase(state)).toBe('over')
    expect(state.request).toBeNull()
  })

  test('a rejected move shows the error and gives the position again, to snap the piece back', () => {
    const sent = gameLoop(humanToMove, { type: 'human-move', uci: 'e2e4' })
    const state = gameLoop(sent, { type: 'failed', requestId: sent.request!.id, message: 'illegal move: e2e5' })

    expect(state.error).toBe('illegal move: e2e5')
    expect(state.request).toBeNull()
    expect(phase(state)).toBe('human')
    expect(state.game).toEqual(humanToMove.game)
    expect(state.game).not.toBe(humanToMove.game)
    expect(state.moveSounds).toBe(humanToMove.moveSounds)
  })

  test('the next move clears the error', () => {
    const sent = gameLoop(humanToMove, { type: 'human-move', uci: 'e2e5' })
    const rejected = gameLoop(sent, { type: 'failed', requestId: sent.request!.id, message: 'illegal move: e2e5' })

    expect(gameLoop(rejected, { type: 'human-move', uci: 'e2e4' }).error).toBeNull()
  })

  test('is ignored when it is not the human to move', () => {
    const waiting = run(received(initialGameLoop, afterE4()))

    expect(gameLoop(waiting, { type: 'human-move', uci: 'e7e5' })).toBe(waiting)
    expect(gameLoop(initialGameLoop, { type: 'human-move', uci: 'e2e4' })).toBe(initialGameLoop)
  })
})

describe('waiting for the LLM', () => {
  const waiting = run(received(initialGameLoop, afterE4()))

  test("the LLM's move lands with its sound, and the human is to move", () => {
    const state = gameLoop(waiting, received(waiting, afterE5()))

    expect(state.game).toEqual(afterE5())
    expect(state.moveSounds).toBe(waiting.moveSounds + 1)
    expect(phase(state)).toBe('human')
    expect(state.request).toBeNull()
  })

  test('a forfeit lands without a sound, and the game is over', () => {
    const forfeit = aTurn('Ke2', {
      attempts: [{ ...aTurn('Ke2').attempts[0], move: null, san: null, result: 'error', error: 'timed out' }],
    })
    const over = afterE4({ llm_turn: forfeit, llm_turns: [forfeit], status: 'over', result: '1-0', end_reason: 'forfeit' })

    const state = gameLoop(waiting, received(waiting, over))

    expect(state.moveSounds).toBe(waiting.moveSounds)
    expect(phase(state)).toBe('over')
    expect(state.request).toBeNull()
  })

  test('a state in which no turn has landed plays no sound', () => {
    // After a 409 the page checks the game until the turn lands; another tab may have started a new game meanwhile.
    const state = gameLoop(waiting, received(waiting, aGame({ game_id: 'game-2' })))

    expect(state.moveSounds).toBe(waiting.moveSounds)
    expect(state.game?.game_id).toBe('game-2')
    expect(phase(state)).toBe('human')
  })

  test('the next LLM turn starts as soon as one lands while an LLM is still to move', () => {
    const black = afterE4().settings.black
    const faceoff = afterE5({ turn: 'black', settings: { ...afterE5().settings, mode: 'llm_faceoff', white: black } })

    const state = gameLoop(waiting, received(waiting, faceoff))

    expect(state.moveSounds).toBe(waiting.moveSounds + 1)
    expect(state.request).toMatchObject({ kind: 'llm-turn' })
    expect(state.request!.id).not.toBe(waiting.request!.id)
  })

  test('a failed turn shows the error and starts no other', () => {
    const state = gameLoop(waiting, { type: 'failed', requestId: waiting.request!.id, message: 'Failed to fetch' })

    expect(state.error).toBe('Failed to fetch')
    expect(state.request).toBeNull()
    expect(state.game).toEqual(afterE4())
    expect(phase(state)).toBe('llm')
  })

  test('the human cannot move', () => {
    expect(gameLoop(waiting, { type: 'human-move', uci: 'e7e5' })).toBe(waiting)
  })
})

describe('new game', () => {
  const settings: NewGame = { mode: 'play_llm', white: { player: 'human' }, black: afterE4().settings.black, rules: 'standard', max_attempts: 5 }
  const waiting = run(received(initialGameLoop, afterE4()))

  test('asks the backend for a game with the settings given, and clears the error', () => {
    const failed = gameLoop(waiting, { type: 'failed', requestId: waiting.request!.id, message: 'Failed to fetch' })

    const state = gameLoop(failed, { type: 'new-game', newGame: settings })

    expect(state.request).toMatchObject({ kind: 'start', newGame: settings })
    expect(state.error).toBeNull()
    expect(state.game).toBe(failed.game) // shown until the new game arrives
  })

  test('shows the new game once it arrives', () => {
    const starting = gameLoop(waiting, { type: 'new-game', newGame: settings })

    const state = gameLoop(starting, received(starting, aGame({ game_id: 'game-2' })))

    expect(state.game?.game_id).toBe('game-2')
    expect(phase(state)).toBe('human')
    expect(state.moveSounds).toBe(waiting.moveSounds)
  })

  test("starts the LLM's first turn when it plays White", () => {
    const starting = gameLoop(waiting, { type: 'new-game', newGame: settings })
    const llmWhite = aGame({
      game_id: 'game-2',
      human_legal_moves: [],
      settings: { ...aGame().settings, white: aGame().settings.black, black: { player: 'human' } },
    })

    const state = gameLoop(starting, received(starting, llmWhite))

    expect(state.request).toMatchObject({ kind: 'llm-turn' })
  })

  test("drops the abandoned game's LLM turn when it lands after New game", () => {
    const abandonedTurn = waiting.request!.id
    const starting = gameLoop(waiting, { type: 'new-game', newGame: settings })
    const started = gameLoop(starting, received(starting, aGame({ game_id: 'game-2' })))

    // llm-turn returns the state of the game it was played in, after the new game has started or before.
    const lateAfterStart = gameLoop(started, { type: 'received', requestId: abandonedTurn, game: afterE5() })
    const lateBeforeStart = gameLoop(starting, { type: 'received', requestId: abandonedTurn, game: afterE5() })

    expect(lateAfterStart).toBe(started)
    expect(lateBeforeStart).toBe(starting)
  })

  test("drops the abandoned game's failed LLM turn too", () => {
    const abandonedTurn = waiting.request!.id
    const starting = gameLoop(waiting, { type: 'new-game', newGame: settings })

    expect(gameLoop(starting, { type: 'failed', requestId: abandonedTurn, message: 'aborted' })).toBe(starting)
  })

  test('when the game cannot start, shows why and the running game goes on, its LLM turn included', () => {
    const starting = gameLoop(waiting, { type: 'new-game', newGame: settings })

    const state = gameLoop(starting, { type: 'failed', requestId: starting.request!.id, message: 'unknown model' })

    expect(state.error).toBe('unknown model')
    expect(state.game).toEqual(afterE4())
    expect(state.request).toMatchObject({ kind: 'llm-turn' })
  })

  test('when the game cannot start and the human is to move, nothing is sent', () => {
    const humanToMove = run(received(initialGameLoop, aGame()))
    const starting = gameLoop(humanToMove, { type: 'new-game', newGame: settings })

    const state = gameLoop(starting, { type: 'failed', requestId: starting.request!.id, message: 'unknown model' })

    expect(state.error).toBe('unknown model')
    expect(phase(state)).toBe('human')
    expect(state.request).toBeNull()
  })

  test('the next LLM turn to start clears the error', () => {
    const black = afterE4().settings.black
    const faceoff = afterE4({ settings: { ...afterE4().settings, mode: 'llm_faceoff', white: black } })
    const playing = run(received(initialGameLoop, faceoff))
    const starting = gameLoop(playing, { type: 'new-game', newGame: settings })
    const refused = gameLoop(starting, { type: 'failed', requestId: starting.request!.id, message: 'unknown model' })

    const landed = afterE5({ turn: 'black', settings: faceoff.settings })
    const state = gameLoop(refused, received(refused, landed))

    expect(state.request).toMatchObject({ kind: 'llm-turn' })
    expect(state.error).toBeNull()
  })

  test('can be asked for during the human move, whose answer is then dropped', () => {
    const humanToMove = run(received(initialGameLoop, aGame()))
    const sent = gameLoop(humanToMove, { type: 'human-move', uci: 'e2e4' })
    const starting = gameLoop(sent, { type: 'new-game', newGame: settings })

    expect(gameLoop(starting, { type: 'received', requestId: sent.request!.id, game: afterE4() })).toBe(starting)
  })

  test('with no settings, asks for the default game', () => {
    expect(gameLoop(waiting, { type: 'new-game', newGame: null }).request).toMatchObject({ kind: 'start', newGame: null })
  })
})

describe('an LLM faceoff', () => {
  const llm = afterE4().settings.black
  const settings = { ...aGame().settings, mode: 'llm_faceoff' as const, white: llm, black: llm }
  const started = aGame({ human_legal_moves: [], settings })
  const turn = (ply: number, color: 'white' | 'black', move: string) => aTurn(move, { ply, color })
  // The game after `plies` LLM turns, each with its legal move.
  const after = (plies: number, overrides: Partial<GameState> = {}): GameState => {
    const turns = Array.from({ length: plies }, (_, i) => turn(i + 1, i % 2 ? 'black' : 'white', `m${i + 1}`))
    return { ...started, turn: plies % 2 ? 'black' : 'white', llm_turns: turns, llm_turn: turns.at(-1) ?? null, ...overrides }
  }
  // Four illegal tries: the side forfeits.
  const forfeitOf = (ply: number, color: 'white' | 'black') =>
    aTurn('Ke2', {
      ply,
      color,
      attempts: Array.from({ length: 4 }, () => ({ ...aTurn('Ke2').attempts[0], result: 'illegal' as const })),
    })
  const playing = run(received(initialGameLoop, started))

  test("asks for White's first turn as soon as the game is shown, and the board takes no move", () => {
    expect(playing.request).toMatchObject({ kind: 'llm-turn', game: started })
    expect(phase(playing)).toBe('llm')
    expect(gameLoop(playing, { type: 'human-move', uci: 'e2e4' })).toBe(playing)
  })

  test('asks for the next turn after each LLM turn, with no pause, until the game is over', () => {
    let state = playing
    const asked: number[] = [state.request!.id]
    for (let plies = 1; plies <= 3; plies++) {
      state = gameLoop(state, received(state, after(plies)))
      expect(state.request).toMatchObject({ kind: 'llm-turn', game: after(plies) })
      asked.push(state.request!.id)
    }
    state = gameLoop(state, received(state, after(4, { status: 'over', result: '1-0', end_reason: 'checkmate' })))

    expect(new Set(asked).size).toBe(4)
    expect(state.moveSounds).toBe(4)
    expect(phase(state)).toBe('over')
    expect(state.request).toBeNull()
  })

  test('stops on New game: the abandoned turn is dropped and no turn of the old game follows', () => {
    const midGame = gameLoop(playing, received(playing, after(1)))
    const abandoned = midGame.request!.id
    const starting = gameLoop(midGame, { type: 'new-game', newGame: null })
    const humanGame = aGame({ game_id: 'game-2' })
    const state = gameLoop(starting, received(starting, humanGame))

    expect(gameLoop(starting, { type: 'received', requestId: abandoned, game: after(2) })).toBe(starting)
    expect(gameLoop(state, { type: 'received', requestId: abandoned, game: after(2) })).toBe(state)
    expect(state.game).toBe(humanGame)
    expect(state.request).toBeNull()
  })

  test.each([
    ['White', 1, 'white', '0-1'],
    ['Black', 2, 'black', '1-0'],
  ] as const)('a forfeit by %s ends it, without a sound, and no turn follows', (_, ply, color, result) => {
    const before = ply === 1 ? playing : gameLoop(playing, received(playing, after(ply - 1)))
    const forfeit = forfeitOf(ply, color)
    const over = after(ply - 1, {
      llm_turn: forfeit,
      llm_turns: [...after(ply - 1).llm_turns, forfeit],
      status: 'over',
      result,
      end_reason: 'forfeit',
    })

    const state = gameLoop(before, received(before, over))

    expect(state.moveSounds).toBe(before.moveSounds)
    expect(phase(state)).toBe('over')
    expect(state.request).toBeNull()
  })
})

describe("the next game's setup", () => {
  test('is set up as the first game shown was, and kept as other games arrive', () => {
    const shown = run(received(initialGameLoop, afterE4()))
    expect(initialGameLoop.next).toBeNull()
    expect(shown.next).toEqual({
      mode: 'play_llm',
      human_color: 'white',
      models: { white: 'qwen3.5:9b', black: 'qwen3.5:9b' },
      custom: false,
      sides: {
        white: { thinking: false, llm_constraints: 'free', retry_feedback: 'explained' },
        black: { thinking: false, llm_constraints: 'free', retry_feedback: 'explained' },
      },
      rules: 'standard',
      max_attempts: 5,
    })

    const changed = { ...shown.next!, mode: 'llm_faceoff' as const }
    const edited = gameLoop(shown, { type: 'next-game', next: changed })
    const landed = gameLoop(edited, received(edited, afterE5()))

    expect(edited.next).toBe(changed)
    expect(landed.next).toBe(changed)
  })
})

describe('when no game can be loaded or started', () => {
  test('stays idle with the error', () => {
    const state = gameLoop(initialGameLoop, { type: 'failed', requestId: 1, message: 'Internal Server Error' })

    expect(phase(state)).toBe('idle')
    expect(state.error).toBe('Internal Server Error')
    expect(state.request).toBeNull()
  })

  test('New game tries again', () => {
    const failed = gameLoop(initialGameLoop, { type: 'failed', requestId: 1, message: 'Internal Server Error' })
    const starting = gameLoop(failed, { type: 'new-game', newGame: null })
    const state = gameLoop(starting, received(starting, aGame()))

    expect(phase(state)).toBe('human')
    expect(state.error).toBeNull()
  })
})

describe('board flashes', () => {
  const waiting = run(received(initialGameLoop, afterE4()))

  test('none until an LLM turn lands', () => {
    expect(initialGameLoop.flash).toBeNull()
    expect(waiting.flash).toBeNull()
  })

  test("an LLM turn that lands flashes that turn, with the square its move landed on", () => {
    const state = gameLoop(waiting, received(waiting, afterE5()))

    expect(state.flash).toEqual({ id: waiting.request!.id, turn: aTurn('e5'), landedOn: 'e5' })
  })

  test('a forfeit flashes too', () => {
    const forfeit = aTurn('Ke2', {
      attempts: [{ ...aTurn('Ke2').attempts[0], move: null, san: null, result: 'error', error: 'timed out' }],
    })
    const over = afterE4({ llm_turn: forfeit, llm_turns: [forfeit], status: 'over', result: '1-0', end_reason: 'forfeit' })

    const state = gameLoop(waiting, received(waiting, over))

    expect(state.flash).toEqual({ id: waiting.request!.id, turn: forfeit, landedOn: 'e4' })
  })

  test('a state in which no turn has landed flashes nothing', () => {
    const state = gameLoop(waiting, received(waiting, aGame({ game_id: 'game-2' })))

    expect(state.flash).toBeNull()
  })

  test("stays up through the human's move, until the next turn lands", () => {
    const landed = gameLoop(waiting, received(waiting, afterE5()))
    const sent = gameLoop(landed, { type: 'human-move', uci: 'g1f3' })
    const moved = gameLoop(sent, received(sent, afterE5({ turn: 'black', pgn: '1. e4 e5 2. Nf3', last_move: 'g1f3' })))

    expect(moved.flash).toBe(landed.flash)

    const next = aTurn('Nc6', { ply: 4 })
    const state = gameLoop(moved, received(moved, afterE5({ pgn: '1. e4 e5 2. Nf3 Nc6', last_move: 'b8c6', llm_turn: next, llm_turns: [aTurn('e5'), next] })))

    expect(state.flash).toEqual({ id: moved.request!.id, turn: next, landedOn: 'c6' })
  })

  test('New game clears them at once', () => {
    const landed = gameLoop(waiting, received(waiting, afterE5()))

    expect(gameLoop(landed, { type: 'new-game', newGame: null }).flash).toBeNull()
  })
})

describe('the move history', () => {
  // 1. e4 e5 2. Nf3: Black (the LLM) to move, its turn running.
  const afterNf3 = afterE5({
    fen: AFTER_NF3,
    pgn: '1. e4 e5 2. Nf3',
    turn: 'black',
    human_legal_moves: [],
    last_move: 'g1f3',
    plies: plies(E4, E5, NF3),
  })
  const live = run(received(initialGameLoop, afterNf3))
  const step = (state: GameLoop, by: -1 | 1, times = 1) =>
    Array.from({ length: times }).reduce<GameLoop>((s) => gameLoop(s, { type: 'step', by }), state)

  test('is live at first: the board shows the game as it is, with its last move', () => {
    expect(live.history).toBeNull()
    expect(shownPosition(live)).toEqual({
      ply: 3, fen: AFTER_NF3, lastMove: 'g1f3', check: false, animateFrom: null, move: afterNf3.plies[2],
    })
  })

  test('← shows the position after the ply before, its move animated from the position before it', () => {
    const state = step(live, -1)

    expect(state.history).toEqual({ ply: 2, news: false })
    expect(shownPosition(state)).toEqual({
      ply: 2, fen: AFTER_E5, lastMove: 'e7e5', check: false, animateFrom: AFTER_E4, move: afterNf3.plies[1],
    })
  })

  test('← goes back as far as the start position, and no further', () => {
    const state = step(live, -1, 5)

    expect(state.history).toEqual({ ply: 0, news: false })
    expect(shownPosition(state)).toEqual({ ply: 0, fen: START, lastMove: null, check: false, animateFrom: null, move: null })
  })

  test('→ steps forward, and past the last ply returns to live', () => {
    const start = step(live, -1, 3)

    const forward = step(start, 1)
    expect(shownPosition(forward)).toMatchObject({ ply: 1, fen: AFTER_E4, lastMove: 'e2e4', animateFrom: START })

    const atLive = step(forward, 1, 2)
    expect(atLive.history).toBeNull()
    expect(step(atLive, 1)).toBe(atLive)
  })

  test('a ply shows the check it gave', () => {
    const checked = { ...afterNf3, plies: afterNf3.plies.map((ply) => ({ ...ply, check: ply.ply === 2 })) }
    const state = step(run(received(initialGameLoop, checked)), -1)

    expect(shownPosition(state)).toMatchObject({ ply: 2, check: true })
  })

  test('clicking a ply shows it, and clicking the last one returns to live', () => {
    const state = gameLoop(live, { type: 'view', ply: 1 })
    expect(shownPosition(state)).toMatchObject({ ply: 1, fen: AFTER_E4, animateFrom: START })

    expect(gameLoop(state, { type: 'view', ply: 3 }).history).toBeNull()
  })

  test('Back to live returns to the game as it is', () => {
    const state = gameLoop(step(live, -1, 2), { type: 'live' })

    expect(state.history).toBeNull()
    expect(shownPosition(state)).toMatchObject({ ply: 3, fen: AFTER_NF3, animateFrom: null })
  })

  test('a game with no plies yet has no past to step into', () => {
    const fresh = run(received(initialGameLoop, aGame()))

    expect(step(fresh, -1)).toBe(fresh)
  })

  test("an LLM move that lands while viewing the past doesn't pull the view, but says something new happened", () => {
    const viewing = step(live, -1, 2)
    const nc6 = aTurn('Nc6', { ply: 4 })
    const landed = afterE5({
      fen: AFTER_NC6,
      pgn: '1. e4 e5 2. Nf3 Nc6',
      last_move: 'b8c6',
      plies: plies(E4, E5, NF3, NC6),
      llm_turn: nc6,
      llm_turns: [aTurn('e5'), nc6],
    })

    const state = gameLoop(viewing, received(viewing, landed))

    expect(state.game).toBe(landed)
    expect(state.history).toEqual({ ply: 1, news: true })
    expect(shownPosition(state)).toMatchObject({ ply: 1, fen: AFTER_E4 })
    expect(shownPosition(gameLoop(state, { type: 'live' }))).toMatchObject({ ply: 4, fen: AFTER_NC6, lastMove: 'b8c6' })
  })

  test('a forfeit while viewing the past adds no ply, but is news too', () => {
    const viewing = step(live, -1)
    const over: GameState = { ...afterNf3, status: 'over', result: '1-0', end_reason: 'forfeit' }

    expect(gameLoop(viewing, received(viewing, over)).history).toEqual({ ply: 2, news: true })
  })

  test('the board takes no move while viewing the past, and does again back at live', () => {
    const humanToMove = run(received(initialGameLoop, afterE5()))
    const viewing = step(humanToMove, -1)

    expect(boardInput(viewing)).toBeNull()
    expect(gameLoop(viewing, { type: 'human-move', uci: 'g1f3' })).toBe(viewing)
    expect(boardInput(gameLoop(viewing, { type: 'live' }))).toBe('white')
    expect(boardInput(humanToMove)).toBe('white')
    expect(boardInput(live)).toBeNull() // the LLM is to move
  })

  test('New game returns to live, as does another game arriving', () => {
    const viewing = step(live, -1)

    expect(gameLoop(viewing, { type: 'new-game', newGame: null }).history).toBeNull()
    expect(gameLoop(viewing, received(viewing, afterE4({ game_id: 'game-2' }))).history).toBeNull()
  })
})
