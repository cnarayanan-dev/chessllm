# Design

The frontend's design system as shipped by the restyle (#52), recorded from the code in `frontend/`. Three surfaces share it: the game page (`/`), the Analytics page (`/analytics`) and the Settings modal. The board keeps its lichess look and is not part of it.

## Style: shadcn Luma

`"style": "base-luma"` in `frontend/components.json` (Base UI primitives, Lucide icons). Its traits, as the installed components in `frontend/src/components/ui/` carry them:

- **Pill controls.** Buttons are `rounded-4xl`; Badges `rounded-3xl`; Switches are wide pills with a pill thumb.
- **Large-radius cards with a soft shadow, no border.** `Card` is `rounded-4xl bg-card shadow-md ring-1 ring-foreground/5`, on a page that is a shade darker than the card, so a card is set off by its fill and shadow rather than a line. `size="sm"` tightens its padding.
- **Filled, borderless surfaces** inside a card: lists, table headers and footers sit on `bg-muted` with a large radius instead of in a box with a border.
- **A near-black primary**: the default Button, the move timer and the turn ring.

The radius scale comes from `--radius: 0.625rem` (`--radius-sm` to `--radius-4xl` in `@theme inline`).

Installed components: Alert, Avatar, Badge, Button, Card, Collapsible (not used yet), Dialog, Item, Kbd, Radio group, Scroll area, Select, Separator, Switch, Table, Tooltip. Add more with `pnpm dlx shadcn@latest add <name>` in `frontend/`.

A link styled as a button merges `buttonVariants` with `cn`, as `Button` does (`linkClass` in `TopBar.tsx`); on their own the variant's classes conflict with the base ones (an `outline` link loses its border).

## Palette: Stone

The `:root` variables in `frontend/src/index.css`: shadcn's lightness steps with stone's warm hue (55 to 80) at very low chroma, so the greys sit with the board's brown wood instead of reading cold next to it. Palette 2 of the prototype (`git show ed4f916:prototypes/game-layout/PALETTES.md`).

| variable | value | role |
| --- | --- | --- |
| `--background` | `oklch(0.963 0.006 75)` | the page, a warm off-white |
| `--foreground`, `--card-foreground`, `--popover-foreground` | `oklch(0.16 0.006 55)` | text |
| `--card`, `--popover` | `oklch(0.997 0.001 90)` | cards, the Dialog, Select popups |
| `--primary` | `oklch(0.23 0.008 55)` | default Button, timer, turn ring, checked Switch |
| `--primary-foreground` | `oklch(0.985 0.002 80)` | text on primary |
| `--secondary`, `--muted` | `oklch(0.948 0.006 70)` | filled surfaces, `secondary` Badges |
| `--secondary-foreground`, `--accent-foreground` | `oklch(0.23 0.008 55)` | text on them |
| `--muted-foreground` | `oklch(0.49 0.012 65)` | secondary text (stock shadcn: `0.556`) |
| `--accent` | `oklch(0.93 0.008 70)` | hover fill |
| `--border`, `--input` | `oklch(0.915 0.006 60)` | the few lines left, unchecked Switch |
| `--ring` | `oklch(0.7 0.012 60)` | focus rings |
| `--destructive` | `oklch(0.54 0.21 27)` | errors, the forfeited Badge |
| `--chart-1` … `--chart-5` | stone greys | not used yet |

The game page's own tokens, available as Tailwind colours (`ring-turn`, `bg-timer`, `text-spawn`, `bg-move-last`, …):

| variable | value | use |
| --- | --- | --- |
| `--turn` | = primary | the ring around the side to move |
| `--timer` / `--timer-foreground` | = primary / primary-foreground | the move timer pill |
| `--slip` | `oklch(0.54 0.12 65)` (amber) | notation slips |
| `--spawn` | `oklch(0.5 0.19 305)` (purple) | Spawns |
| `--move-olive` | `oklch(0.69 0.13 110)` | the board's last-move olive; the pulse of a new move |
| `--move-last` | `color-mix(in oklab, var(--move-olive) 22%, var(--card))` | the latest move in the list |
| `--move-viewed` | `color-mix(in oklab, var(--move-olive) 48%, var(--card))` | the move viewed in the history |

The move-list highlights are mixed from the board's own last-move colour, so the list and the board point at the same move in the same colour.

Dark mode is out of scope: `.dark` keeps shadcn's neutral values and nothing switches to it.

### Contrast

WCAG 2.x ratios of the shipped values (AA: 4.5:1 for text, 3:1 for non-text). "Tested" marks the pairs `frontend/src/theme.test.ts` checks; the others were measured once and no test guards them.

| pair | ratio | tested |
| --- | --- | --- |
| foreground on background / card / muted | 17.4 / 19.3 / 16.7 | background and card (card-foreground) only |
| muted-foreground on background / card / muted / accent | 5.6 / 6.2 / 5.4 / 5.1 | yes (also popover, secondary) |
| primary-foreground on primary (buttons); timer-foreground on timer | 16.2 | yes |
| secondary-foreground on secondary; accent-foreground on accent | 14.5 / 15.8 | yes |
| destructive on card / muted | 5.6 / 4.8 | card only |
| slip / spawn on card | 5.2 / 6.6 | yes |
| slip on its chip tint (8% slip in card) | 4.65 | no |
| foreground on `--move-last` / `--move-viewed` | 15.9 / 12.4 | no |
| turn ring on card (non-text) | 16.8 | no |
| white on the monogram colours (`logos.ts`) | 5.5 to 11.4 | no |
| the move list's red `#e03e3e` on its chip tint `#fbe4e4` / on muted | **3.5 / 3.7, fails AA** | no |

Stock shadcn neutral's muted foreground (`#737373`) fails AA on a grey page (about 4.3:1), which is why it is darker here.

**Known gap**: the Moves panel's illegal-try and forfeit chips and its chaos moves, and the chaos caption under the board, still use the old page's raw red (`--red: #e03e3e`, `--red-soft: #fbe4e4` in `moves.css`; the same values in `board.css`) instead of `--destructive`, and it fails AA as above.

Checks: `frontend/src/theme.test.ts` (with `frontend/src/test/contrast.ts`) reads `:root` from `index.css` and checks, at 4.5:1, `muted-foreground` on background, card, popover, muted, secondary and accent; each of foreground, card, popover, primary, secondary, accent and timer with its own `-foreground`; `destructive`, `slip` and `spawn` on card; and that the card stands out from the page (over 1.05:1). `frontend/e2e/analytics.e2e.ts` measures every text on the built Analytics page against the surface under it, all layers composited; nothing does that for the game page.

## Type: Inter

**Inter** (`@fontsource-variable/inter`, bundled, no CDN) is `--font-sans` and `--font-heading`, so the only interface face. Numbers that line up or tick use tabular figures (`tabular-nums`: the timer, +N, the move list, the Analytics numbers).

The scale in use: 14px body (`text-sm` on the page), 15px in the Game card and Reasoning panel, 16px moves and strip names, 18px the ChessLLM name, 20px the result line and the timer, 24px the Analytics title. Headings are sentence case at `font-semibold` with `tracking-tight` on the larger ones. Secondary text is `text-muted-foreground`, never a smaller uppercase label.

The board keeps its own small face for the coordinates and its flashes (`board.css`, `flashes.css`).

## Icons: Lucide

All interface icons are Lucide (`lucide-react`), with `aria-hidden` next to a text label. In use on the game page and Analytics: `ChartNoAxesColumn` Analytics, `Plus` New game, `Settings2` Settings and the pending-settings Badge, `Swords` Play LLM, `Bot` LLM faceoff, `ArrowRight` the result's New game, `User` the human, `Sparkles` spawned pieces, `X` illegal tries, `PenLine` notation slips, `TriangleAlert` a forfeit's error, `Zap` chaos moves, `ArrowUp` / `ArrowDown` the sorted column. In the Settings modal: `Swords` Game, `Bot` Model and `SlidersHorizontal` Advanced for its sections, and `ArrowLeftRight` to swap the sides. Chess pieces are drawn with the Merida set, never as Unicode glyphs.

## Layout

### Top bar

`frontend/src/components/top-bar/TopBar.tsx`, on every page, everything on the left: the **ChessLLM** mark (the Merida rook on a light square, `frontend/src/assets/chessllm-rook.svg`, also the browser tab's icon in `frontend/index.html`) linking to the game, then **Analytics** (`ghost`, filled `muted` on its own page), **New game** (`outline`) and **Settings** (`ghost`). ⌘K shows only in the Settings button's Tooltip ("Settings" + `Kbd`). On a page without the game, New game and Settings (and ⌘K) link to the game page with `?then=new-game` / `?then=settings`, which does it once the game is shown. No settings show in the top bar.

The page footer is one muted line of credits: the Merida pieces, the move sound and the model logos.

### Game page

`frontend/src/components/game-layout/GameLayout.tsx` and `game-layout.css`, a CSS grid of three areas (max 1680px, 32px gaps):

| window | columns | order |
| --- | --- | --- |
| over 1100px | **¼ \| ½ \| ¼** | Game card and Reasoning panel · board with its strips · Moves |
| 760 to 1100px | 3fr \| 2fr | the board on the left; Moves, then the Game card and Reasoning panel under them, on the right |
| under 760px | one | board, Moves, Game card, Reasoning panel |

The board column is a stack at the board's width, `min(100%, 100svh - 206px)`, so the board fits the window's height together with a player strip above and below it; what sits directly above and below the board takes its width. Under 760px the stack is the full width.

**Orientation** (`orientation` in `frontend/src/game/gameLoop.ts`): in **Play LLM** the human's side is at the bottom; in an **LLM faceoff** White is.

Before a game exists, an error starting one shows as a `destructive` Alert in the left column.

## Components per box

| Box | Components |
| --- | --- |
| Top bar | ghost / outline `Button`s (links as `buttonVariants`), `Tooltip` + `Kbd` |
| Game card | `Card`, `CardHeader` / `CardTitle` / `CardContent`, `Separator`, `Button size="lg"`, `Badge variant="secondary"` |
| Reasoning panel | `Card`, `CardHeader` / `CardTitle` / `CardContent`, `Badge` (`secondary`, or `destructive` when forfeited) |
| Player strip | `Item` holding a pill with `Avatar` / `AvatarFallback`; Merida pieces; `Badge variant="secondary"` for +N |
| Board | cm-chessboard in `Board.tsx`, unchanged |
| Moves panel | `Card size="sm"`, `CardTitle`, `Switch size="sm"`, `ScrollArea` |
| Start error | `Alert variant="destructive"` |
| Analytics | `Card` with `CardHeader` / `CardContent` / `CardFooter`, `Switch`, `Table`, `Badge` (`secondary` chips, dashed `outline` mark), `Tooltip` |
| Settings modal | `Dialog`, `Button`, `Badge`, `Select`, `Radio group`, `Switch`, `Tooltip` |

## Player strip

`frontend/src/components/player-strip/PlayerStrip.tsx`, directly above and below the board, for the side on that edge. Left-aligned in an `Item`:

1. **The turn pill**: a `card` pill (`h-11`, `shadow-xs ring-1 ring-foreground/5`) with the side's icon and name (16px, semibold, truncated). The side to move gets `shadow-md ring-2 ring-turn`. The ring follows the live game, also while a past position is viewed, and is gone once the game is over.
2. **The icon** (`Avatar`): the model family's logo on a card-coloured disc (`frontend/src/assets/logos/`, LobeHub Icons, MIT: Qwen, Meta for llama, Gemma, Mistral for mistral/ministral, DeepSeek), matched on the Ollama name without its registry path and before its version or first separator (`qwen3.5:9b` → qwen; `logos.ts`). Any other family gets a white monogram on one of eight colours, fixed per family by a hash of its name. The human has a Lucide `User` and the name "You".
3. **What the side has on the board** (`Captures.tsx`): the pieces it took as small Merida pieces of the other colour (smallest first, the same kind overlapping), then the pieces it spawned, in its own colour, in a `spawn`-tinted pill with `Sparkles`, then **+N** as a `secondary` Badge on the side ahead only.
4. **The move timer**, right-aligned (`MoveTimer`): a `bg-timer` pill, 20px tabular figures, counting whole seconds, only during an LLM's move, in every Mode, in the strip of the LLM to move. On the human's move there is only the ring.

All of 3 is of the position on the board, so stepping through the move history changes it. It is counted ply by ply from each ply's `fen_before` / `fen_after` piece letters (`frontend/src/game/material.ts`; no chess logic, ADR 0001): a capture is a piece of the other side that disappeared on the side's ply; a spawn is a piece of its own that appeared beyond what its promotions explain (on a Spawn ply every new piece counts as spawned), so a Spawn never hides a capture. A piece a chaos move takes of its own side shows only in +N. +N is the material difference on the board shown (1/3/3/5/9), so it adds up from what the strips show; under Standard rules it is the usual lichess display.

There is no sentence saying whose move it is: the ring and the timer say it.

## Game card

`frontend/src/components/game-card/GameCard.tsx`, top of the left column, a lichess game card without Elo, 15px:

- **Header**: the Mode icon (`Swords` Play LLM, `Bot` LLM faceoff) in a 40px `muted` circle, beside the **Mode** as the `CardTitle` and, under it in muted text, the **settings line** (`settingsLine` in `frontend/src/game/wording.ts`): LLM constraints, rules, retry feedback, thinking, and the illegal moves before a forfeit when not the default, e.g. `Listed | Standard rules | explained feedback | thinking off`. A value that differs between the two LLMs gives one item per side ("White thinking off | Black thinking on"). Items are flex items that wrap only between each other; the "|" sits in each item's left padding and the list is shifted left by that padding, so no line starts with a "|".
- **Players**, indented under the Mode: a small outlined circle for White and a filled one for Black (drawn in CSS, with the side named for screen readers), then the model or "You". No Elo.
- **When the game is over**, after a `Separator`: the **result line** (20px semibold, e.g. "Black wins by checkmate", or in a faceoff by model, "qwen3.5:9b (White) wins by checkmate") with the reason's detail under it in muted text, and a primary `Button size="lg"` "New game →". This replaces the old result banner.
- **Last**, when there is one: a `secondary` Badge with `Settings2`, "Your changes apply to the next game", and a request error as a `text-destructive` line.

## Reasoning panel

`frontend/src/components/reasoning/ReasoningPanel.tsx`, a `Card` under the Game card, 15px. The header is the title **Reasoning** and a `secondary` Badge naming the LLM and the move: "qwen3.5:9b · 10… Nxa1", or in a faceoff "White · gemma3:4b · 1. e4". Under it the **Reasoning** (CONTEXT.md) in the card's foreground, relaxed leading, line breaks kept.

It follows the position on the board, live or in the move history: on an LLM's move its Reasoning; on the human's move or the start position, the LLM's last move before it, else a muted "The LLM has not moved yet." ("No LLM has moved yet." in a faceoff). It shows only the Reasoning of the turn's last attempt (the one played); illegal tries stay as chips in the Moves panel. Live after a Forfeit, the Badge is `destructive`, "… · forfeited", over the last attempt's Reasoning. With thinking on, or a last attempt with no answer, a quiet muted line says why there is none.

The Thinking itself is not shown anywhere; it stays in the API and the game log.

## Moves panel

`frontend/src/components/moves/MovesCard.tsx` and `moves.css`, a `Card size="sm"` in the right column:

- **Header**: the title **Moves**, and right-aligned a small Switch, "Show LLM mistakes", kept in `localStorage` across games.
- **The list**, in a `ScrollArea` on a filled `muted` surface (18px radius) of a set height: 8 rows of 34px with 2px gaps and 6px padding. A grid of the move number (13px, muted) and two plies per row, 16px, weight 500, tabular. Each ply is a button with a 10px radius that views the position after it. The latest move is tinted `--move-last`, the move viewed `--move-viewed`; hover is `--accent`. A notation slip has an inset 1px `--slip` line; under Chaos rules a chaos move is in red (the raw red under Known gap, in Contrast) and a Spawn in `--spawn`, as the LLM wrote them.
- **Mistake chips**, with the switch on, in a row under the move they belong to (these rows come on top of the 8): illegal tries in red with `X` and the move struck through ("Nf7 illegal · try 1"), a forfeit's error in red with `TriangleAlert`, a notation slip in amber with `PenLine` ('written "…"'). 12px, small radius.
- **Totals**, with the switch on, under a faint line, 12px muted: illegal tries (`X`, or "illegal tries n/a" under Enforced decoding, ADR 0003), notation slips (`PenLine`) and under Chaos rules chaos moves with their spawns (`Zap`), one line per LLM side, named "White · model" / "Black · model" in a faceoff.

Scrolling: to the latest move when live; while a past position is viewed, just enough to keep the move viewed in view (the start position: the top). It scrolls only when a move or a try lands, or the view or the switch changes, so a reader who scrolled up is left there.

There is no Back to live button: → up to the latest move, or clicking it, returns to the live position, and a new move never pulls the view back. Instead the new move **pulses**: an inset 2px `--move-olive` ring, two 0.8s beats, stopping early once the view is back at live; held still under `prefers-reduced-motion`.

## Board

Unchanged by the restyle (`frontend/src/components/board/`): cm-chessboard with the lichess look (`#f0d9b5` / `#b58863` squares, olive last-move tint, green dots, check glow), Merida pieces, the move sound. Its flashes (`flashes.css`: the centre card of an LLM turn's mistakes, the amber slip bubble) and the chaos caption under the board (`board.css`, red for a chaos move, `--spawn` for a Spawn) keep the old page's look.

## Analytics page

`frontend/src/analytics/AnalyticsPage.tsx`, max 1400px: the top bar with Analytics marked, the title **Leaderboard** (24px semibold) and a muted line under it, then the leaderboard in one `Card`:

- **Header**: the legend of chips and the "All columns" Switch.
- **The table**: its header row is a filled `muted` strip with rounded ends (12px muted labels, the sorted one in foreground with a Lucide arrow); rows are split by faint lines only (`border-border/70`), numbers right-aligned in tabular figures.
- **Chips**: `secondary` Badges in muted text; a chip with a hue (`analytics.css`: one per LLM constraints, green for thinking on) is in the foreground with a coloured dot and a light tint of its hue. The unvalidated Move-quality estimate is a dashed `outline` Badge with a Tooltip.
- **Footer**: the note in muted 12px.

Loading, no games and errors each show in a plain Card in the table's place.

## Settings modal

Only its style is part of this system (its content changes separately): a `Dialog` (`rounded-4xl`, `shadow-xl`), a `muted` side rail of pill section buttons with the current one on `card`, filled choice cards (`rounded-2xl bg-muted`, chosen: `card` with a 2px primary ring), Luma Selects and Switches, and a `muted` footer strip with the primary "Start new game" Button.

## Patterns this replaced

The React port (#29) carried the old page's generic look. These are gone; don't bring them back.

| Replaced | With |
| --- | --- |
| Stock shadcn neutral theme, whose secondary text fails AA on a grey page | The Stone palette, warm greys with a darker muted foreground, checked by tests |
| Every block in a bordered card | Luma cards set off by fill and shadow; inside them filled `muted` surfaces, and faint lines only between table rows and above the totals |
| Glyph icons (♞ ⚙ ✦ ⚑ …) | Lucide icons; the Merida rook as the mark and tab icon; Merida pieces for captures |
| A row of setting chips in the top bar | The settings line in the Game card, items separated by "\|" |
| Uppercase micro-labels | Sentence-case `CardTitle`s and muted text |
| Status sentences ("Black · qwen3.5:9b is thinking… 12s", "Your move", "Waiting for…") | The turn ring and the move timer in the player strips |
| The result banner | The result line and New game button in the Game card |
| Players shown only as chips | Player strips with logo, name, captures, spawns and +N |
| A move list that grows with the game, and Back to live | A fixed-height list of 8 rows that scrolls itself, and the pulse on a new move |
| "Show thinking" | The Reasoning panel (the Thinking stays in the API and the log) |
