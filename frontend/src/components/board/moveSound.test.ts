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

test('the move sound is on unless switched off, and plays the click', () => {
  expect(isMoveSoundOn()).toBe(true)

  playMoveSound()

  expect(played).toEqual(['/static/sounds/move.mp3'])
})

test('switched off, the move sound stays silent, and the browser remembers it', () => {
  setMoveSoundOn(false)

  playMoveSound()

  expect(played).toEqual([])
  expect(localStorage.getItem('chessllm.moveSound')).toBe('off') // the key the old page used
  expect(isMoveSoundOn()).toBe(false)
})

test('a browser that refuses to play the sound is not an error', async () => {
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockRejectedValue(new DOMException('no click yet', 'NotAllowedError'))

  expect(() => playMoveSound()).not.toThrow()
  await new Promise((resolve) => setTimeout(resolve))
})
