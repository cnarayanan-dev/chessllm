// One sound for every legal move, the human's and the LLM's. A page setting, kept in the browser across games and
// reloads under the old page's key.
const MOVE_SOUND_KEY = 'chessllm.moveSound'

let moveSound: HTMLAudioElement | null = null

export function isMoveSoundOn(): boolean {
  return localStorage.getItem(MOVE_SOUND_KEY) !== 'off'
}

export function setMoveSoundOn(on: boolean) {
  localStorage.setItem(MOVE_SOUND_KEY, on ? 'on' : 'off')
}

export function playMoveSound() {
  if (!isMoveSoundOn()) return
  moveSound ??= new Audio('/static/sounds/move.mp3')
  moveSound.currentTime = 0
  moveSound.play().catch(() => {}) // the browser may refuse until the page has had a click
}
