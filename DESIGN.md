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

## Game page

`frontend/src/components/game-layout/GameLayout.tsx` lays the page out in three columns, **¼ | ½ | ¼**: the Game card and the Reasoning panel under it on the left, the board in the middle, the moves on the right. There is no status line. "Show thinking" is hidden for now; the Thinking stays in the API and the game log. From 1100px down to 760px it is two columns (the board, and the moves with the Game card under them); below 760px one column (board, moves, Game card). The board column is a stack at the board's width, which fits the window's height, so what goes directly above and below the board (the player strips) has its width.

The board shows the human's side at the bottom in **Play LLM**, White in an **LLM faceoff** (`orientation` in `frontend/src/game/gameLoop.ts`).

The **player strips** (`frontend/src/components/player-strip/PlayerStrip.tsx`), directly above and below the board at its width, for the side on that edge: a pill (Avatar and name, on `card` with a soft shadow) holding the side's icon and name, left-aligned, then what follows the name (the captures, spawns and +N), and the move timer on the right. The icon is the model family's logo (`frontend/src/assets/logos/`, from LobeHub Icons, MIT, credited in the page footer), matched on the Ollama name before its version (`qwen3.5:9b` → Qwen; llama → Meta), else a white monogram on a colour fixed per family; the human has a Lucide `User` and "You". The side to move has a 2px `ring-turn` around its pill, following the live game also while a past position is viewed; none once the game is over. The **move timer** (`bg-timer` pill, tabular figures) counts the seconds only during an LLM's move, in every Mode; on the human's move there is only the ring. There is no status line for whose move it is.

After the name (`Captures.tsx`): the pieces the side took, as small Merida pieces (smallest first, the same kind overlapping), then the pieces it spawned on the same pieces in its own colour, in a `spawn`-tinted pill with a Lucide `Sparkles`, then **+N** as a `secondary` Badge on the side ahead only. All of it is of the position on the board, so stepping through the move history changes it. It is counted ply by ply from each ply's `fen_before` / `fen_after` piece letters (`frontend/src/game/material.ts`, no chess logic, ADR 0001): a capture is a piece of the other side that disappeared on the side's ply (a taken king too, after a King capture); a spawn is a piece of its own that appeared on its ply beyond the promotions its lost pawns explain (on a Spawn ply every new piece is spawned, since the spawned piece may land on a pawn of its own). A piece a chaos move takes of its own side shows only in +N. +N is the material difference on the board shown, 1/3/3/5/9.

The **Game card** (`frontend/src/components/game-card/GameCard.tsx`), a lichess game card without Elo: a Mode icon (Lucide `Swords` for Play LLM, `Bot` for LLM faceoff) and the Mode, then the settings separated by "|" (each item on one line, so the line wraps only between items, and no "|" starts a line; a value that differs between the two LLMs gives one item per side), then the players as ○ White / ● Black. When the game is over, the result line and a New game button follow a Separator. The "changes apply to the next game" note and request errors go last.

The **Reasoning panel** (`frontend/src/components/reasoning/ReasoningPanel.tsx`), a Card under the Game card: the title "Reasoning" and a `secondary` Badge with the model (and side first, in a faceoff, e.g. "White · gemma3:4b · 1. e4") and the move, e.g. "qwen3.5:9b · 10… Nxa1", then the turn's Reasoning (its last attempt's: the one played) in the card's foreground. It follows the position on the board, live or in the move history: on an LLM's move its Reasoning, on the human's move the LLM's last move before it, at the start "The LLM has not moved yet". Live after a Forfeit the Badge is `destructive`, "… · forfeited", over the last attempt's Reasoning. With thinking on, or an attempt with no answer, a quiet muted line says there is none.

The **Moves** card (`frontend/src/components/moves/MovesCard.tsx`): its title, "Moves", in normal case like the other cards' titles, and the "Show LLM mistakes" Switch, then the move list in a Scroll area on a filled `muted` surface, of a set height of 8 rows of 34px (rows of mistake chips come on top), the moves in 16px. The latest move is tinted `--move-last`, the move viewed in the history `--move-viewed`. The list scrolls to the latest move, or, while a past position is viewed, just enough to keep the move viewed in view. There is no Back to live: → up to the latest move, or clicking it, returns to the live position, and a new move never pulls the view back; it pulses instead, a ring in `--move-olive`, for 1.6s or until the view is back at live (held still under reduced motion). The list scrolls only when a move or a try lands, or the view or the switch changes, so a user who scrolled up to read is left there. The mistake chips and the totals under the list carry Lucide icons: `X` for illegal tries, `PenLine` for notation slips, `TriangleAlert` for a forfeit's error and `Zap` for chaos moves; in a faceoff each side's totals are named "White · model" / "Black · model".

## Analytics page

`frontend/src/analytics/AnalyticsPage.tsx`: the page's title on the Stone page, then the leaderboard in one Card: the legend and the "All columns" Switch, the Table and its note. The table's header row is a filled `muted` strip with rounded ends, its rows are split by faint lines only, and the sorted column carries a Lucide arrow. The chips are `secondary` Badges, tinted by their hue (`analytics.css`); the unvalidated Move-quality estimate is marked by a dashed `outline` Badge. Loading, no games and errors show in a Card in the table's place. `frontend/e2e/analytics.e2e.ts` checks every text on the built page against WCAG AA, on the surface it sits on.
