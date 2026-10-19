// New game and Settings in the top bar of a page without the game: links to the game page, which does it once loaded.

/** What the game page does once loaded, when New game or Settings was chosen on another page. */
export type Then = 'new-game' | 'settings'

/** The game page's address that starts a new game or opens the Settings modal there. */
export const thenHref = (then: Then) => `/?then=${then}`

/** What a link from another page asked the game page to do, if anything. */
export function thenFrom(search: string): Then | null {
  const then = new URLSearchParams(search).get('then')
  return then === 'new-game' || then === 'settings' ? then : null
}
