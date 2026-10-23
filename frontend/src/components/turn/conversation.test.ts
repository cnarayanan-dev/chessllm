import { expect, test } from 'vitest'
import type { Attempt, LlmTurn } from '@/api/types'
import { conversationPrompt, counterpartPrompt, fullPrompt, messagesOf } from '@/components/turn/conversation'
import fixture from '@/components/turn/conversation.fixture.json'

// Scripted games' records and every Prompt their LLMs were sent, the backend's full_prompt and counterpart_prompt
// checked against the same (tests/game/test_conversation_fixture.py). In "trimmed" White keeps a conversation, trimmed
// at its 3rd turn and within its 4th, Black plays fresh; in "chaos" each side's chaos move has a Legal counterpart,
// White's asked in its conversation, Black's fresh; in "moves" White chats with moves under Retry feedback repeat; in
// "aside" White's counterpart was trimmed to the context on its own.
const turns = fixture.trimmed.llm_turns as LlmTurn[]
const turnAt = (ply: number) => turns.find((turn) => turn.ply === ply)!

test("every attempt's whole Prompt is rebuilt from the records as the LLM received it, fresh or in a conversation", () => {
  for (const game of Object.values(fixture)) {
    const played = game.llm_turns as LlmTurn[]
    for (const sent of game.prompts) {
      const turn = played.find((each) => each.ply === sent.ply)!
      expect(fullPrompt(played, turn, sent.attempt), `ply ${sent.ply}, attempt ${sent.attempt}`).toEqual(sent.prompt)
    }
  }
})

test("a Legal counterpart's whole Prompt: in a conversation its chaos move's turn whole, then the request", () => {
  for (const game of Object.values(fixture)) {
    const played = game.llm_turns as LlmTurn[]
    for (const sent of game.counterparts) {
      const turn = played.find((each) => each.ply === sent.ply)!
      expect(messagesOf(counterpartPrompt(played, turn)), `ply ${sent.ply}`).toEqual(sent.prompt)
    }
  }
  const played = fixture.chaos.llm_turns as LlmTurn[]
  const white = counterpartPrompt(played, played[0])
  expect(white.current.map((message) => message.label)).toEqual(['Turn 1', 'Answer', 'Legal counterpart request'])
})

test('the turns dropped to fit the context are named, by their number in the side\'s turns', () => {
  const trimmed = (ply: number, attempt: number) => conversationPrompt(turns, turnAt(ply), attempt).trimmed

  expect(trimmed(3, 1)).toBeNull()
  expect(trimmed(5, 1)).toEqual({ from: 1, to: 1 })
  expect(trimmed(7, 1)).toEqual({ from: 1, to: 1 })
  expect(trimmed(7, 2)).toEqual({ from: 1, to: 2 }) // trimmed again within the turn
  expect(trimmed(9, 1)).toEqual({ from: 1, to: 2 })
})

test('the earlier turns remembered are numbered and labelled, then this turn up to the attempt', () => {
  const prompt = conversationPrompt(turns, turnAt(7), 2)

  expect(prompt.system?.content).toBe('You play White.')
  expect(prompt.earlier.map((turn) => turn.number)).toEqual([3])
  expect(prompt.earlier[0].messages.map((message) => message.label)).toEqual(['Turn 3', 'Answer'])
  expect(prompt.current.map((message) => message.label)).toEqual(['Turn 4', 'Answer', 'Retry feedback'])
})

test('a fresh Prompt is as recorded, the position and each Retry labelled as before', () => {
  const prompt = conversationPrompt(turns, turnAt(2), 1)

  expect(prompt).toMatchObject({ trimmed: null, earlier: [] })
  expect(prompt.system?.role).toBe('system')
  expect(prompt.current.map((message) => message.label)).toEqual(['Position'])
})

test('under Retry feedback repeat a rejected answer is left out of the conversation', () => {
  const attempt = (raw_reply: string, prompt: Attempt['prompt'], feedback_sent: string | null = null) =>
    ({ ...turnAt(1).attempts[0], raw_reply, prompt, feedback_sent }) as Attempt
  const first = turnAt(1)
  const repeated: LlmTurn = {
    ...turnAt(3),
    attempts: [attempt('{"move": "Qxf7"}', [{ role: 'user', content: '1. f3 e5' }]), attempt('{"move": "g4"}', [])],
  }

  expect(fullPrompt([first, repeated], repeated, 2)).toEqual([
    { role: 'system', content: 'You play White.' },
    { role: 'user', content: '(no moves yet)' },
    { role: 'assistant', content: '{"move": "f3"}' },
    { role: 'user', content: '1. f3 e5' },
  ])
})

test("a Legal counterpart trimmed to the context on its own is marked so, its chaos move's turn not", () => {
  const played = fixture.aside.llm_turns as LlmTurn[]
  const chaosTurn = played.find((turn) => turn.ply === 3)!

  expect(conversationPrompt(played, chaosTurn, 1).trimmed).toBeNull()
  expect(counterpartPrompt(played, chaosTurn).trimmed).toEqual({ from: 1, to: 1 })
})
