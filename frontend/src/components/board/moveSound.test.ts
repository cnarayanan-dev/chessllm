import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { isMoveSoundOn, playMoveSound, setMoveSoundOn } from '@/components/board/moveSound'

let played: string[]

beforeEach(() => {
  played = []
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockImplementation(function (this: HTMLMediaElement) {
    played.push(new URL(this.src).pathname)
    return Promise.resolve()
  })
})

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

test('the move sound is off in a browser that never switched it on', () => {
  expect(isMoveSoundOn()).toBe(false)

  playMoveSound()

  expect(played).toEqual([])
})

test('switched on, the move sound plays the click, and the browser remembers it', () => {
  setMoveSoundOn(true)

  playMoveSound()

  expect(localStorage.getItem('chessllm.moveSound')).toBe('on')
  expect(isMoveSoundOn()).toBe(true)

  expect(played).toEqual(['/static/sounds/move.mp3'])
})

test('switched off again, the move sound stays silent, and the browser remembers it', () => {
  setMoveSoundOn(true)
  setMoveSoundOn(false)

  playMoveSound()

  expect(played).toEqual([])
  expect(localStorage.getItem('chessllm.moveSound')).toBe('off') // the key the old page used
  expect(isMoveSoundOn()).toBe(false)
})

test('a browser that refuses to play the sound is not an error', async () => {
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockRejectedValue(new DOMException('no click yet', 'NotAllowedError'))
  setMoveSoundOn(true)

  expect(() => playMoveSound()).not.toThrow()
  await new Promise((resolve) => setTimeout(resolve))
})
