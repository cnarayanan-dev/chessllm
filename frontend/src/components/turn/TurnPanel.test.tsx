import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import type { Attempt, LlmTurn } from '@/api/types'
import { TurnPanel } from '@/components/turn/TurnPanel'
import { aTurn, afterE4, afterE5, chaosGame, E4, E5, NF3, NC6, plies } from '@/test/games'

beforeEach(() => localStorage.clear())

const panel = () => screen.getByRole('region', { name: 'Turn' })
const badge = () => within(panel()).getByTestId('turn-move').textContent
const tab = (name: string) => within(panel()).getByRole('tab', { name })

/** 1. e4 e5 2. Nf3 Nc6, the LLM's e5 and Nc6 each with its Reasoning. */
const twoMovesIn = () =>
  afterE5({ plies: plies(E4, E5, NF3, NC6), llm_turns: [aTurn('e5'), aTurn('Nc6', { ply: 4 })] })

test('opens on the Reasoning of the LLM move on the board, the badge naming only the move', () => {
  render(<TurnPanel game={twoMovesIn()} ply={4} live />)

  expect(badge()).toBe('2… Nc6')
  expect(tab('Reasoning')).toHaveAttribute('aria-selected', 'true')
  expect(within(panel()).getByText('Reasoning for Nc6.')).toBeVisible()
})

test("on the human's move, the LLM's last move before it; at the start position, none yet", () => {
  const { rerender } = render(<TurnPanel game={twoMovesIn()} ply={3} live={false} />)

  expect(badge()).toBe('1… e5')
  expect(within(panel()).getByText('Reasoning for e5.')).toBeVisible()

  rerender(<TurnPanel game={twoMovesIn()} ply={1} live={false} />)

  expect(within(panel()).queryByTestId('turn-move')).not.toBeInTheDocument()
  expect(within(panel()).getByText('The LLM has not moved yet.')).toBeVisible()
})

/** An attempt of the LLM's turn, with the given move, result and Reasoning. */
const anAttempt = (
  move: string | null,
  result: Attempt['result'],
  reasoning: string | null,
  error: string | null = null,
): Attempt => ({ ...aTurn('e5').attempts[0], move, san: result === 'legal' ? move : null, result, reasoning, error })

/** 1. e4, then the LLM forfeits: its last attempt is the one given. */
const forfeited = (last: Attempt) => {
  const turn = aTurn('e5', {
    attempts: [anAttempt('Qh4', 'illegal', 'The queen attacks f2.'), last],
    reasoning: last.reasoning,
  })
  return afterE4({ status: 'over', result: '1-0', end_reason: 'forfeit', llm_turn: turn, llm_turns: [turn] })
}

test("live after a Forfeit, the last attempt's Reasoning, marked as forfeited", () => {
  render(<TurnPanel game={forfeited(anAttempt('Kd6', 'illegal', 'The king leads.'))} ply={1} live />)

  expect(badge()).toBe('forfeited')
  expect(within(panel()).getByText('The king leads.')).toBeVisible()
})

test('an attempt with no answer has no Reasoning, and says so', () => {
  const timeout = anAttempt(null, 'timeout', null, 'Too long thinking: qwen3.5:9b gave no answer within 5 minutes.')
  render(<TurnPanel game={forfeited(timeout)} ply={1} live />)

  expect(within(panel()).getByText('It gave no answer, so there is no Reasoning.')).toBeVisible()
})

test('in the move history the forfeited turn is not shown: it has no move on the board', () => {
  render(<TurnPanel game={forfeited(anAttempt('Kd6', 'illegal', 'The king leads.'))} ply={1} live={false} />)

  expect(within(panel()).getByText('The LLM has not moved yet.')).toBeVisible()
})

test('in a faceoff the badge still names only the move', () => {
  const llm = { player: 'llm', model: 'qwen3.5:9b', thinking: false, llm_constraints: 'free', retry_feedback: 'explained' } as const
  const game = afterE5({
    settings: { ...afterE5().settings, mode: 'llm_faceoff', white: { ...llm, model: 'gemma3:4b' }, black: llm },
    llm_turns: [aTurn('e4', { ply: 1, color: 'white' }), aTurn('e5')],
  })
  const { rerender } = render(<TurnPanel game={game} ply={1} live={false} />)

  expect(badge()).toBe('1. e4')
  expect(within(panel()).getByText('Reasoning for e4.')).toBeVisible()

  rerender(<TurnPanel game={game} ply={0} live={false} />)

  expect(within(panel()).getByText('No LLM has moved yet.')).toBeVisible()
})

test('with thinking on, the tab is Thinking and shows the Thinking of the attempt played', () => {
  const game = twoMovesIn()
  const black = { ...game.settings.black, thinking: true }
  const nc6 = aTurn('Nc6', { ply: 4 })
  const thought = { ...nc6.attempts[0], thinking: 'Develop and defend e5.', reasoning: null }
  const turns = [aTurn('e5'), { ...nc6, attempts: [thought], thinking: thought.thinking, reasoning: null }]
  render(<TurnPanel game={{ ...game, settings: { ...game.settings, black }, llm_turns: turns }} ply={4} live />)

  expect(tab('Thinking')).toHaveAttribute('aria-selected', 'true')
  expect(within(panel()).queryByRole('tab', { name: 'Reasoning' })).not.toBeInTheDocument()
  expect(within(panel()).getByText('Develop and defend e5.')).toBeVisible()
})

const SYSTEM = 'You are playing chess as Black against a human playing White.'
const POSITION = 'PGN: 1. e4\nFEN: rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1'

/** 1. e4 e5, the LLM's e5 with the Prompt it was sent. */
const withPrompt = () => {
  const turn = aTurn('e5')
  const prompt = [
    { role: 'system', content: SYSTEM },
    { role: 'user', content: POSITION },
  ] as const
  const recorded = { ...turn, attempts: [{ ...turn.attempts[0], prompt: [...prompt] }] }
  return afterE5({ llm_turn: recorded, llm_turns: [recorded] })
}

test('the Prompt tab shows the messages sent, the System prompt folded and the position open', async () => {
  render(<TurnPanel game={withPrompt()} ply={2} live />)

  await userEvent.click(tab('Prompt'))

  expect(within(panel()).getByText(/^PGN: 1\. e4/)).toBeVisible()
  expect(within(panel()).queryByText(SYSTEM)).not.toBeInTheDocument()

  await userEvent.click(within(panel()).getByRole('button', { name: /System prompt/ }))

  expect(within(panel()).getByText(SYSTEM)).toBeVisible()
})

test('a turn from before prompts were recorded says so in the Prompt tab', async () => {
  render(<TurnPanel game={twoMovesIn()} ply={4} live />)

  await userEvent.click(tab('Prompt'))

  expect(within(panel()).getByText('The Prompt was not recorded for this turn.')).toBeVisible()
})

test('the Answer tab shows the raw reply with its result and how long it took', async () => {
  render(<TurnPanel game={twoMovesIn()} ply={4} live />)

  await userEvent.click(tab('Answer'))

  expect(within(panel()).getByText(/"move": "Nc6"/)).toBeVisible()
  expect(within(panel()).getByText('Legal · 1.2 s')).toBeVisible()
})

test("a failed attempt's Answer shows why it has no reply", async () => {
  const timeout = anAttempt(null, 'timeout', null, 'Too long thinking: qwen3.5:9b gave no answer within 5 minutes.')
  render(<TurnPanel game={forfeited({ ...timeout, raw_reply: null, latency_s: null })} ply={1} live />)

  await userEvent.click(tab('Answer'))

  expect(within(panel()).getByText('Too long thinking: qwen3.5:9b gave no answer within 5 minutes.')).toBeVisible()
  expect(within(panel()).getByText('Timeout')).toBeVisible()
})

test('a turn with retries opens on its last attempt, and the stepper switches every tab to another', async () => {
  const turn = aTurn('e5', {
    attempts: [anAttempt('Qh4', 'illegal', 'The queen attacks f2.'), anAttempt('e5', 'legal', 'Take the centre.')],
    reasoning: 'Take the centre.',
  })
  render(<TurnPanel game={afterE5({ llm_turn: turn, llm_turns: [turn] })} ply={2} live />)

  expect(within(panel()).getByText('Attempt 2 of 2')).toBeVisible()
  expect(within(panel()).getByText('Take the centre.')).toBeVisible()

  await userEvent.click(within(panel()).getByRole('button', { name: 'Earlier attempt' }))

  expect(within(panel()).getByText('Attempt 1 of 2')).toBeVisible()
  expect(within(panel()).getByText('The queen attacks f2.')).toBeVisible()
  await userEvent.click(tab('Answer'))
  expect(within(panel()).getByText('Illegal · 1.2 s')).toBeVisible()
})

test('a turn with one attempt has no stepper', () => {
  render(<TurnPanel game={twoMovesIn()} ply={4} live />)

  expect(within(panel()).queryByRole('button', { name: 'Earlier attempt' })).not.toBeInTheDocument()
})

describe('Legal counterpart', () => {
  const AFTER_E5 = 'rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2'
  type LegalCounterpart = NonNullable<LlmTurn['legal_counterpart']>
  const MEANING = 'The legal move the LLM gave when asked once more in the same position, after its Chaos move. Never played.'

  /** 1. e4 Bb4, a Chaos move, its turn with the Legal counterpart given; then, with `more`, 2. c3. */
  const withCounterpart = (counterpart: LegalCounterpart, more = 0) => {
    const game = chaosGame(2 + more)
    const turns = game.llm_turns.map((turn) => (turn.ply === 2 ? { ...turn, legal_counterpart: counterpart } : turn))
    return { ...game, llm_turns: turns, llm_turn: turns.at(-1)! }
  }
  const e5: LegalCounterpart = {
    move: 'e7e5',
    san: 'e5',
    fen_after: AFTER_E5,
    attempt: { ...aTurn('e5').attempts[0], latency_s: 3.4 },
  }
  const block = () => within(panel()).queryByRole('group', { name: 'Legal counterpart' })

  test("viewing a Chaos move, the panel ends with its Legal counterpart's move, its meaning in a tooltip", async () => {
    render(<TurnPanel game={withCounterpart(e5)} ply={2} live />)

    const name = within(block()!).getByText('Legal counterpart')
    expect(name).toHaveAttribute('aria-description', MEANING)
    expect(name.querySelector('svg')).toBeInTheDocument()
    expect(within(block()!).getByTestId('counterpart-move')).toHaveTextContent('1… e5')
    expect(block()).not.toHaveTextContent('3.4') // no time is shown
    expect(panel()).not.toHaveTextContent('Never played')
    await userEvent.hover(name)
    expect((await screen.findByText(MEANING)).closest('[data-slot=tooltip-content]')).toBeInTheDocument()
  })

  test("the counterpart's move is a toggle that says on focus what it shows, and when pressed, how to go back", async () => {
    const onPreview = vi.fn()
    const { rerender } = render(<TurnPanel game={withCounterpart(e5)} ply={2} live onPreview={onPreview} />)
    const move = within(block()!).getByRole('button', { name: '1… e5' })
    expect(move).toHaveAttribute('aria-pressed', 'false')

    for (let i = 0; i < 20 && document.activeElement !== move; i++) await userEvent.tab()
    const show = 'Show the position 1… e5 would have left on the board. It was never played.'
    expect((await screen.findByText(show)).closest('[data-slot=tooltip-content]')).toBeInTheDocument()
    expect(move).toHaveAttribute('aria-description', show)
    await userEvent.keyboard('{Enter}')
    expect(onPreview).toHaveBeenCalledOnce()

    rerender(<TurnPanel game={withCounterpart(e5)} ply={2} live previewing onPreview={onPreview} />)

    expect(move).toHaveAttribute('aria-pressed', 'true')
    expect(move).toHaveAttribute('aria-description', 'Back to 1… Bb4 on the board.')
  })

  test('viewing the next ply, the Chaos move is still the turn shown, but its counterpart is not', () => {
    render(<TurnPanel game={withCounterpart(e5, 1)} ply={3} live />)

    expect(badge()).toBe('1… Bb4')
    expect(block()).not.toBeInTheDocument()
  })

  test('a Chaos move without a Legal counterpart has no such line', () => {
    render(<TurnPanel game={chaosGame(2)} ply={2} live />)

    expect(block()).not.toBeInTheDocument()
  })

  test('a failed Legal counterpart says it gave none, and why in its tooltip', () => {
    const error = 'Too long thinking: qwen3.5:9b gave no answer within 5 minutes.'
    const failed = { move: null, san: null, fen_after: null, attempt: { ...e5.attempt, result: 'timeout', error } } as const
    render(<TurnPanel game={withCounterpart(failed)} ply={2} live />)

    const none = within(block()!).getByTestId('counterpart-move')
    expect(none).toHaveTextContent('none')
    expect(none).toHaveAttribute('aria-description', error)
  })
})

describe('Chaos gain', () => {
  type ChaosGain = NonNullable<LlmTurn['chaos_gain']>
  const MEANING =
    'How much breaking the rules gained the LLM: the Evaluation after its Chaos move minus the one after its Legal counterpart, in pawns from its side. Capped at ±20.'
  const e5 = {
    move: 'e7e5',
    san: 'e5',
    fen_after: 'rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2',
    attempt: aTurn('e5').attempts[0],
  }
  const gain = (vs_counterpart: number | null): ChaosGain => ({
    best_evaluation: { pawns: 0.3, mate: null, unjudged: null },
    vs_counterpart,
    vs_best: 4.2,
  })
  /** 1. e4 Bb4, a Chaos move, with its Legal counterpart and the gain given; the switch on unless `switchOn` is false. */
  const withGain = (chaosGain: ChaosGain | undefined, switchOn = true) => {
    const game = chaosGame(2)
    const turns = game.llm_turns.map((turn) => ({ ...turn, legal_counterpart: switchOn ? e5 : undefined, chaos_gain: chaosGain }))
    return { ...game, llm_turns: turns, llm_turn: turns.at(-1)!, settings: { ...game.settings, legal_counterpart: switchOn } }
  }
  const line = () => within(panel()).queryByRole('group', { name: 'Chaos gain' })
  const value = () => within(line()!).getByTestId('chaos-gain')
  const icon = () => line()!.querySelector('svg')

  test('under the Legal counterpart, the gain over it with a rising icon, its meaning in a tooltip', async () => {
    render(<TurnPanel game={withGain(gain(6.6))} ply={2} live />)

    expect(value()).toHaveTextContent('+6.6')
    expect(icon()).toHaveClass('lucide-trending-up')
    expect(panel()).not.toHaveTextContent('4.2') // never the gain over Stockfish's best move
    const counterpart = within(panel()).getByRole('group', { name: 'Legal counterpart' })
    expect(counterpart.compareDocumentPosition(line()!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    const name = within(line()!).getByText('Chaos gain')
    expect(name).toHaveAttribute('aria-description', MEANING)
    await userEvent.hover(name)
    expect((await screen.findByText(MEANING)).closest('[data-slot=tooltip-content]')).toBeInTheDocument()
  })

  test('a loss with a falling icon and a minus sign, no gain with a flat one', () => {
    const { rerender } = render(<TurnPanel game={withGain(gain(-19.6))} ply={2} live />)
    expect(value()).toHaveTextContent('−19.6')
    expect(icon()).toHaveClass('lucide-trending-down')

    rerender(<TurnPanel game={withGain(gain(0))} ply={2} live />)
    expect(value()).toHaveTextContent('0.0')
    expect(icon()).toHaveClass('lucide-minus')
  })

  test('a gain not judged says so, and why in its tooltip', () => {
    render(<TurnPanel game={withGain(gain(null))} ply={2} live />)

    expect(value()).toHaveTextContent('not judged')
    expect(value()).toHaveAttribute('aria-description', expect.stringMatching(/no Evaluation/))
  })

  test('its meaning opens on keyboard focus too', async () => {
    render(<TurnPanel game={withGain(gain(6.6))} ply={2} live />)

    within(line()!).getByText('Chaos gain').focus()
    expect((await screen.findByText(MEANING)).closest('[data-slot=tooltip-content]')).toBeInTheDocument()
  })

  test('a Legal counterpart that gave no move has no gain line', () => {
    const game = withGain(gain(null))
    const failed = { ...e5, move: null, san: null, fen_after: null }
    const turns = game.llm_turns.map((turn) => ({ ...turn, legal_counterpart: failed }))
    render(<TurnPanel game={{ ...game, llm_turns: turns, llm_turn: turns.at(-1)! }} ply={2} live />)

    expect(line()).not.toBeInTheDocument()
  })

  test('with the switch off, or before the gain is worked out, there is no such line', () => {
    const { rerender } = render(<TurnPanel game={withGain(gain(6.6), false)} ply={2} live />)
    expect(line()).not.toBeInTheDocument()

    rerender(<TurnPanel game={withGain(undefined)} ply={2} live />)
    expect(line()).not.toBeInTheDocument()
  })
})

test('the tab chosen stays chosen on the next turn and after a reload', async () => {
  const { rerender, unmount } = render(<TurnPanel game={twoMovesIn()} ply={4} live />)
  await userEvent.click(tab('Answer'))

  rerender(<TurnPanel game={twoMovesIn()} ply={2} live={false} />)

  expect(tab('Answer')).toHaveAttribute('aria-selected', 'true')
  expect(within(panel()).getByText(/"move": "e5"/)).toBeVisible()

  unmount()
  render(<TurnPanel game={twoMovesIn()} ply={4} live />)

  expect(tab('Answer')).toHaveAttribute('aria-selected', 'true')
})
