import { render, screen, within } from '@testing-library/react'
import { expect, test } from 'vitest'
import type { Attempt } from '@/api/types'
import { ReasoningPanel } from '@/components/reasoning/ReasoningPanel'
import { aTurn, afterE4, afterE5, E4, E5, NF3, NC6, plies } from '@/test/games'

const panel = () => screen.getByRole('region', { name: 'Reasoning' })
const heading = () => within(panel()).getByTestId('reasoning-move').textContent

/** 1. e4 e5 2. Nf3 Nc6, the LLM's e5 and Nc6 each with its Reasoning. */
const twoMovesIn = () =>
  afterE5({ plies: plies(E4, E5, NF3, NC6), llm_turns: [aTurn('e5'), aTurn('Nc6', { ply: 4 })] })

test('shows the Reasoning of the LLM move on the board, headed by the model and the move', () => {
  render(<ReasoningPanel game={twoMovesIn()} ply={4} live />)

  expect(heading()).toBe('qwen3.5:9b · 2… Nc6')
  expect(within(panel()).getByText('Reasoning for Nc6.')).toBeVisible()
})

test("on the human's move, the LLM's last move before it; at the start position, none yet", () => {
  const { rerender } = render(<ReasoningPanel game={twoMovesIn()} ply={3} live={false} />)

  expect(heading()).toBe('qwen3.5:9b · 1… e5')
  expect(within(panel()).getByText('Reasoning for e5.')).toBeVisible()

  rerender(<ReasoningPanel game={twoMovesIn()} ply={1} live={false} />)

  expect(within(panel()).queryByTestId('reasoning-move')).not.toBeInTheDocument()
  expect(within(panel()).getByText('The LLM has not moved yet.')).toBeVisible()
})

/** An attempt of the LLM's turn, with the given move, result and Reasoning. */
const anAttempt = (
  move: string | null,
  result: Attempt['result'],
  reasoning: string | null,
  error: string | null = null,
): Attempt => ({ ...aTurn('e5').attempts[0], move, san: result === 'legal' ? move : null, result, reasoning, error })

test('only the Reasoning of the attempt that was played', () => {
  const turn = aTurn('e5', {
    attempts: [anAttempt('Qh4', 'illegal', 'The queen attacks f2.'), anAttempt('e5', 'legal', 'Take the centre.')],
    reasoning: 'Take the centre.', // the turn's Reasoning is its last attempt's, as the backend sends it
  })
  render(<ReasoningPanel game={afterE5({ llm_turn: turn, llm_turns: [turn] })} ply={2} live />)

  expect(within(panel()).getByText('Take the centre.')).toBeVisible()
  expect(within(panel()).queryByText('The queen attacks f2.')).not.toBeInTheDocument()
})

/** 1. e4, then the LLM forfeits: its last attempt is the one given. */
const forfeited = (last: Attempt) => {
  const turn = aTurn('e5', {
    attempts: [anAttempt('Qh4', 'illegal', 'The queen attacks f2.'), last],
    reasoning: last.reasoning,
  })
  return afterE4({ status: 'over', result: '1-0', end_reason: 'forfeit', llm_turn: turn, llm_turns: [turn] })
}

test("live after a Forfeit, the last attempt's Reasoning, marked as forfeited", () => {
  render(<ReasoningPanel game={forfeited(anAttempt('Kd6', 'illegal', 'The king leads.'))} ply={1} live />)

  expect(heading()).toBe('qwen3.5:9b · forfeited')
  expect(within(panel()).getByText('The king leads.')).toBeVisible()
})

test('a Forfeit with no answer has no Reasoning, and says so', () => {
  const timeout = anAttempt(null, 'timeout', null, 'Too long thinking: qwen3.5:9b gave no answer within 5 minutes.')
  render(<ReasoningPanel game={forfeited(timeout)} ply={1} live />)

  expect(heading()).toBe('qwen3.5:9b · forfeited')
  expect(within(panel()).getByText('It gave no answer, so there is no Reasoning.')).toBeVisible()
})

test('in the move history the forfeited turn is not shown: it has no move on the board', () => {
  render(<ReasoningPanel game={forfeited(anAttempt('Kd6', 'illegal', 'The king leads.'))} ply={1} live={false} />)

  expect(within(panel()).getByText('The LLM has not moved yet.')).toBeVisible()
})

test('with thinking on, a quiet line says there is no Reasoning', () => {
  const game = twoMovesIn()
  const black = { ...game.settings.black, thinking: true }
  render(<ReasoningPanel game={{ ...game, settings: { ...game.settings, black } }} ply={4} live />)

  expect(heading()).toBe('qwen3.5:9b · 2… Nc6')
  expect(within(panel()).getByText('qwen3.5:9b plays with thinking on, so it gives no Reasoning.')).toBeVisible()
  expect(within(panel()).queryByText('Reasoning for Nc6.')).not.toBeInTheDocument()
})

test('in a faceoff the heading names the side too', () => {
  const llm = { player: 'llm', model: 'qwen3.5:9b', thinking: false, llm_constraints: 'free', retry_feedback: 'explained' } as const
  const game = afterE5({
    settings: { ...afterE5().settings, mode: 'llm_faceoff', white: { ...llm, model: 'gemma3:4b' }, black: llm },
    llm_turns: [aTurn('e4', { ply: 1, color: 'white' }), aTurn('e5')],
  })
  const { rerender } = render(<ReasoningPanel game={game} ply={1} live={false} />)

  expect(heading()).toBe('White · gemma3:4b · 1. e4')
  expect(within(panel()).getByText('Reasoning for e4.')).toBeVisible()

  rerender(<ReasoningPanel game={game} ply={0} live={false} />)

  expect(within(panel()).getByText('No LLM has moved yet.')).toBeVisible()
})
