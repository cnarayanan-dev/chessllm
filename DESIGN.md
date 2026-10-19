# Design

The frontend's look, as set in the restyle (#52). The board keeps its lichess look (brown squares, olive last move, Merida pieces) and is never restyled with the rest.

## Style

shadcn's **Luma** style (`"style": "base-luma"` in `frontend/components.json`): pill buttons (`rounded-4xl`), large-radius cards with a soft shadow (`rounded-4xl shadow-md ring-1 ring-foreground/5`), filled borderless surfaces (`bg-muted`, inputs on `bg-input/50`) and a near-black primary. Icons are Lucide, not text glyphs.

Installed components (`frontend/src/components/ui/`): Alert, Avatar, Badge, Button, Card, Collapsible, Dialog, Item, Kbd, Radio group, Scroll area, Select, Separator, Switch, Table, Tooltip. Add more with `pnpm dlx shadcn@latest add <name>` in `frontend/`.

When a link is styled as a button, merge `buttonVariants` with `cn` as `Button` does; on its own its classes conflict (an `outline` link loses its border).

## Font

**Inter** (`@fontsource-variable/inter`, bundled, no CDN) is the only interface font, with tabular figures where numbers line up. Only the board keeps its own small face for the coordinates and the flashes over it.

## Palette: Stone

The variables in `:root` of `frontend/src/index.css`: shadcn's lightness steps with stone's warm hue (55 to 80) at very low chroma, so the greys sit with the board's wood instead of against it. The page is a warm off-white (`--background`), cards are near-white (`--card`), filled surfaces use `--muted`.

The muted foreground is darker than stock shadcn (`oklch(0.49 0.012 65)` instead of `0.556`), so secondary text passes WCAG AA on the page, cards and filled surfaces (5.6, 6.2 and 5.4:1). `frontend/src/theme.test.ts` checks every text and surface pair of the palette.

The game page's own tokens, usable as Tailwind colours (`bg-timer`, `ring-turn`, `text-spawn`, ...):

| token | use |
| --- | --- |
| `--turn` | the ring around the side to move (= primary) |
| `--timer` / `--timer-foreground` | the move timer pill (= primary) |
| `--slip` | notation slips (amber) |
| `--spawn` | Spawns (purple) |
| `--move-last` / `--move-viewed` | move-list highlights, mixed from the board's last-move olive (`--move-olive`) |

Dark mode is out of scope; `.dark` keeps shadcn's neutral values.

## Top bar

`frontend/src/components/top-bar/TopBar.tsx`, on every page: the **ChessLLM** mark (the Merida rook on a light square, `frontend/src/assets/chessllm-rook.svg`, also the browser tab's icon) linking to the game, then **Analytics**, **New game** and **Settings** on the left. The ⌘K shortcut shows only in the Settings button's tooltip. On a page without the game, New game and Settings (and ⌘K) are links to the game page (`/?then=new-game`, `/?then=settings`), which does it once the game is shown.
