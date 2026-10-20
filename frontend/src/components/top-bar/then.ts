// New game in the top bar of a page without the game: a link to the game page, which opens the New game sheet once loaded.

/** What the game page does once loaded, when New game was chosen on another page. */
export type Then = 'new-game'

/** The game page's address that opens the New game sheet there. */
export const thenHref = (then: Then) => `/?then=${then}`

/** What a link from another page asked the game page to do, if anything. */
export function thenFrom(search: string): Then | null {
  return new URLSearchParams(search).get('then') === 'new-game' ? 'new-game' : null
}
