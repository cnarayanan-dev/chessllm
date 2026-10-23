# Design

The frontend's design system as shipped by the restyle (#52), recorded from the code in `frontend/`. Three surfaces share it: the game page (`/`), the Analytics page (`/analytics`) and the New game sheet. The board keeps its lichess look and is not part of it.

## Rules for the whole UI

- **Icon and short name, the explanation on hover.** A choice or control shows an icon and its short name. Its description, hint, or the reason it is disabled appears in a `Tooltip` on hover and on keyboard focus, and the same text is the control's `aria-description` for screen readers. No secondary text lines under options. The trigger is the control itself, or a row holding the control's name and the control (as Move sound in Preferences), so hovering the name and focusing the control both show it.
- **Icons: Lucide** for every interface icon, **Lobe Icons** for model logos (as in the player strips). No other icon set; an icon Lucide lacks is drawn in Lucide's line style (e.g. thinking off is Lucide `Brain` with a slash, as Lucide draws its `*Off` icons). No text glyphs (♔ ♚ ⇄ ▸).

## Style: shadcn Luma

`"style": "base-luma"` in `frontend/components.json` (Base UI primitives, Lucide icons). Its traits, as the installed components in `frontend/src/components/ui/` carry them:

- **Pill controls.** Buttons are `rounded-4xl`; Badges `rounded-3xl`; Switches are wide pills with a pill thumb.
- **Large-radius cards with a soft shadow, no border.** `Card` is `rounded-4xl bg-card shadow-md ring-1 ring-foreground/5`, on a page that is a shade darker than the card, so a card is set off by its fill and shadow rather than a line. `size="sm"` tightens its padding.
- **Filled, borderless surfaces** inside a card: lists, table headers and footers sit on `bg-muted` with a large radius instead of in a box with a border.
- **A near-black primary**: the default Button, the move timer and the turn ring.

The radius scale comes from `--radius: 0.625rem` (`--radius-sm` to `--radius-4xl` in `@theme inline`).

Installed components: Alert, Avatar, Badge, Button, Card, Collapsible, Dialog, Item, Kbd, Popover, Radio group, Scroll area, Select, Separator, Switch, Table, Tabs, Tooltip. Add more with `pnpm dlx shadcn@latest add <name>` in `frontend/`.

A link styled as a button merges `buttonVariants` with `cn`, as `Button` does (`linkClass` in `TopBar.tsx`); on their own the variant's classes conflict with the base ones (an `outline` link loses its border).

## Palette: Stone

The `:root` variables in `frontend/src/index.css`: shadcn's lightness steps with stone's warm hue (55 to 80) at very low chroma, so the greys sit with the board's brown wood instead of reading cold next to it. Palette 2 of the prototype (`git show ed4f916:prototypes/game-layout/PALETTES.md`).

| variable | value | role |
| --- | --- | --- |
| `--background` | `oklch(0.963 0.006 75)` | the page, a warm off-white |
| `--foreground`, `--card-foreground`, `--popover-foreground` | `oklch(0.16 0.006 55)` | text |
| `--card`, `--popover` | `oklch(0.997 0.001 90)` | cards, the Dialog, Select popups, the Preferences panel |
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

**Known gap**: the Moves panel's illegal-try and forfeit chips and its chaos moves (muted from that red) still use the old page's raw red (`--red: #e03e3e`, `--red-soft: #fbe4e4` in `moves.css`) instead of `--destructive`, and it fails AA as above.

Checks: `frontend/src/theme.test.ts` (with `frontend/src/test/contrast.ts`) reads `:root` from `index.css` and checks, at 4.5:1, `muted-foreground` on background, card, popover, muted, secondary and accent; each of foreground, card, popover, primary, secondary, accent and timer with its own `-foreground`; `destructive`, `slip` and `spawn` on card; and that the card stands out from the page (over 1.05:1). `frontend/e2e/analytics.e2e.ts` measures every text on the built Analytics page against the surface under it, all layers composited; nothing does that for the game page.

## Type: Inter

**Inter** (`@fontsource-variable/inter`, bundled, no CDN) is `--font-sans` and `--font-heading`, so the only interface face. Numbers that line up or tick use tabular figures (`tabular-nums`: the timer, +N, the move list, the Analytics numbers).

The scale in use: 14px body (`text-sm` on the page), 15px in the Game card (the result line too) and Turn panel, 16px moves and strip names, 18px the ChessLLM name, 20px the timer, 24px the Analytics title. Headings are sentence case at `font-semibold` with `tracking-tight` on the larger ones. Secondary text is `text-muted-foreground`, never a smaller uppercase label.

The board keeps its own small face for the coordinates and its flashes (`board.css`, `flashes.css`).

## Icons: Lucide

All interface icons are Lucide (`lucide-react`), with `aria-hidden` next to a text label. In use on the game page and Analytics: `ChartNoAxesColumn` Analytics, `Plus` New game, `Settings` (the gear) Preferences, `User` vs `Bot` Play LLM and `Bot` vs `Bot` LLM faceoff in the Game card (the Rules chip and the setting icons: Game card), `RotateCcw` the result's Rematch, `User` the human, `Sparkles` spawned pieces, `X` illegal tries (and under Chaos rules illegal moves), `PenLine` notation slips, `TriangleAlert` a forfeit's error, `Scale` the Legal counterpart in the Turn panel, `ArrowUp` / `ArrowDown` the sorted column. In the New game sheet: `User` vs `Bot` and `Bot` vs `Bot` on the Mode cards, the Game card's setting icons on the Rules, constraint and Retry feedback cards, `ArrowLeftRight` to swap the sides and `ChevronDown` on Advanced settings. Chess pieces are drawn with the Merida set, never as Unicode glyphs.

## Layout

### Top bar

`frontend/src/components/top-bar/TopBar.tsx`, on every page: on the left the **ChessLLM** mark (the Merida rook on a light square, `frontend/src/assets/chessllm-rook.svg`, also the browser tab's icon in `frontend/index.html`) linking to the game, then **Analytics** (`ghost`, filled `muted` on its own page) and **New game** (`outline`), and on the right (`ml-auto`) the gear **Preferences** icon button (below). New game and ⌘K (Ctrl+K) open the New game sheet; ⌘K shows only in New game's Tooltip ("New game" + `Kbd`). On a page without the game, New game (and ⌘K) link to the game page with `?then=new-game` (`frontend/src/components/top-bar/then.ts`), which opens the sheet there once the game (or the empty board) is shown and drops the parameter. No game settings show in the top bar; Preferences holds only this browser's own choices.

### Preferences

`frontend/src/components/top-bar/Preferences.tsx`, the same on every page: a `ghost` `size="icon"` Button with Lucide `Settings` (the gear), named "Preferences" for screen readers and in its Tooltip. It opens a `Popover` (`w-64`, aligned to its end, so it opens leftwards under the gear) titled **Preferences**, holding the preferences of this browser rather than of a game:

- **Move sound**: its name and a `Switch` on one row, the explanation "A click on every move. Applies at once, in this browser." in a Tooltip on the row (hover, and focus on the switch) and as the switch's `aria-description`. It applies at once and is kept in `localStorage` (`chessllm.moveSound`, `frontend/src/components/board/moveSound.ts`), **off by default**: on only when stored as `'on'`.

Opening the panel moves focus to its first control; Esc or a click outside closes it.

The page footer is one muted line of credits: the Merida pieces, the move sound and the model logos.

### Game page

`frontend/src/components/game-layout/GameLayout.tsx` and `game-layout.css`, a CSS grid of three areas (max 1680px, 32px gaps):

| window | columns | order |
| --- | --- | --- |
| over 1100px | **¼ \| ½ \| ¼**; over 1100 × 600, the board's own width between two equal side columns (see below) | Game card and Turn panel · board with its strips · Moves |
| 760 to 1100px | 3fr \| 2fr | the board on the left; Moves, then the Game card and Turn panel under them, on the right |
| under 760px | one | board, Moves, Game card, Turn panel |

The board column is a stack at the board's width, `min(100%, 100svh - var(--around-board))`, so the board fits the window's height together with what is around it (`--around-board`, whose parts the CSS lists: the top bar, the page's top padding, a player strip above and below it with their gaps, and a little room under the lower strip); what sits directly above and below the board takes its width. Under 760px the stack is the full width. In an LLM faceoff the **Evaluation bar** (below) stands left of the board, in the gap before the board column, so the board and its strips keep their width; under 760px, with no such gap, the board makes room for it. Nothing sits under the board: a chaos move shows only as its arrow and a Spawn as its ring, on the board, and the resolver's reason is not shown.

**On a wide window** (over 1100 × 600) the page fits the window, with no page scroll: the page is the window's height, and `--around-board` takes in the page's bottom padding and the footer too. The board is as large as the window's height allows, but no wider than the larger of half the row and the row less two side columns of `--side-min` (300px): on a tall window the side columns keep `--side-min` while the board grows past half, on a narrow one the board stops at half, and on a short one the height decides and the side columns take the rest. The board column is as wide as the board, and the side columns share the rest equally. The Game card keeps its size, the Turn panel under it scrolls inside itself, and the Moves card is the Game card's height (`--top-card`, 290px), so the Turn panel and the mistakes card start level. The Game card is taller only when a player's row holds that side's own settings.

**Orientation** (`orientation` in `frontend/src/game/gameLoop.ts`): in **Play LLM** the human's side is at the bottom; in an **LLM faceoff** White is.

Before a game exists, an error starting one shows as a `destructive` Alert in the left column.

## Components per box

| Box | Components |
| --- | --- |
| Top bar | ghost / outline `Button`s (links as `buttonVariants`), `Tooltip` + `Kbd`; Preferences: icon `Button`, `Popover`, `Switch`, `Tooltip` |
| Game card | `Card`, `CardHeader` / `CardTitle` / `CardContent`, `Separator`, `SettingChip` with `Tooltip` (Rematch: its button form), `Tooltip` on the result line and the settings text, `Badge variant="secondary"` |
| Turn panel | `Card`, `CardHeader` / `CardTitle` / `CardContent`, `Badge` (`secondary`, or `destructive` when forfeited or not legal), `Tabs` (`line`), `Collapsible`, ghost icon `Button`s |
| Player strip | `Item` holding a pill with `Avatar` / `AvatarFallback`; Merida pieces; `Badge variant="secondary"` for +N |
| Board | cm-chessboard in `Board.tsx`, unchanged |
| Evaluation bar | a `meter` with `Tooltip` |
| Moves panel | `Card size="sm"`, `CardTitle`, `Switch size="sm"`, `ScrollArea` |
| Start error | `Alert variant="destructive"` |
| Analytics | `Card` with `CardHeader` / `CardContent` / `CardFooter`, `Switch`, `Table`, `Badge` (`secondary` chips, dashed `outline` mark), `Tooltip` |
| New game sheet | `Dialog`, `Radio group` cards, `Select`, `Switch`, `Collapsible`, `Button`, `Tooltip` |

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

- **Header**: the **Mode icon shows the players**, in a 64 × 40px `muted` pill: Lucide `User` "vs" `Bot` for Play LLM, `Bot` "vs" `Bot` for LLM faceoff (`role="img"`, named "You against an LLM" / "An LLM against an LLM"). Beside it the **Mode** as the `CardTitle` and, under it:
  - **The Rules**, whether the game is wild, the one setting shown: a labelled setting chip, `ChessKnight` "Standard rules" or `Zap` "Chaos rules", its meaning in the tooltip.

  The settings the LLMs share are not shown, to keep the card simple. In a faceoff a setting the two LLMs differ in is on each **player's row**, after the model, as a line of 13px muted text without the side, " · " between items, wrapping as needed ("qwen3.8:latest  Thinking on"): the LLM constraints ("Shown and kept legal (Listed enforced)", the sheet's plain name and the glossary term), the Retry feedback (none for an LLM under an enforced constraint), Thinking on / off, and the forfeit limit ("Forfeit after 5 illegal moves"). Each item is focusable, its name (semibold) and meaning in a `Tooltip` and its `aria-description` (the hover rule). The names, meanings and per-side split come from `gameSettings` in `frontend/src/game/wording.ts`; the setting icons (`settingIcon` in `frontend/src/components/game-card/settingIcons.ts`) are also the New game sheet's: LLM constraints Free `Eye`, Listed `ListChecks`, Blind enforced `Lock`, Listed enforced `ShieldCheck`; Rules Standard `ChessKnight`, Chaos `Zap`; Retry feedback Explained `MessageSquareText`, Bare `MessageSquare`, Hinted `Lightbulb`, Repeat `Repeat`; Thinking `Brain` / `BrainOff` (Lucide's `Brain` with the slash of its *Off icons, `frontend/src/components/icons/BrainOff.tsx`); the forfeit limit `Flag`.
- **Players**, indented under the Mode: a small outlined circle for White and a filled one for Black (drawn in CSS, with the side named for screen readers), then the model or "You", and in a faceoff the settings that side differs in. No model logo (the strips have them), no Elo.
- **The setting chip** (`SettingChip` in `frontend/src/components/setting-chip/SettingChip.tsx`), for any small round control or badge in this style: a 28px `muted` circle holding one 16px Lucide icon (stroke 1.75), focusable so its `Tooltip` opens on hover and on keyboard focus. Given `labelled` (the Rules), a `muted` pill with the icon and its name beside it. Given `onClick`, it is a `button` instead: a `muted` pill with the icon and its name beside it, hover `accent`, the tooltip giving only the description.
- **The result**, after a `Separator`, in a space of the same height whether the game is playing or over, so the card never grows when the game ends: while playing, a muted "Playing" holds the room. Once over, the **result line** (15px semibold, up to two lines, e.g. "Black wins by checkmate", or in a faceoff by model, "qwen3.5:9b (White) wins by checkmate"); its detail, such as a forfeit's reason or the king left hanging, is in a `Tooltip` on hover and keyboard focus and in its `aria-description`, the line focusable only when it has one. Under it **Rematch**: a setting chip button, `RotateCcw` and "Rematch". **Rematch** (CONTEXT.md) starts a new game at once, no sheet, with the same Mode and settings and the colours swapped: in Play LLM the human takes the other colour, so the board turns; in a faceoff the two LLMs change sides, each with its own settings. Its tooltip and `aria-description` say what happens: "Same settings, you play Black" / "… you play White" / "Same settings, the LLMs swap colours" (`rematchOf` and `rematchDescription` in `frontend/src/game/rematch.ts`). New game stays in the top bar. This replaces the old result banner.
- **Last**, when there is one: a request error as a `text-destructive` line. There is no note about the next game's settings: the New game sheet starts the game it sets up, or forgets its changes.

## Turn panel

`frontend/src/components/turn/TurnPanel.tsx`, a `Card` under the Game card, 15px. The header is the title **Turn** and a `secondary` Badge naming only the move, "10… Nxa1": the board and the player strips already say whose it is. Under it three line `Tabs`, each a Lucide icon and a short name, what it holds in its tooltip and `aria-description`:

- **Thinking** (`Brain`) with thinking on, or **Reasoning** with it off: the attempt's **Thinking** or **Reasoning** (CONTEXT.md) in the card's foreground, relaxed leading, line breaks kept. With no answer, a muted line says why there is none.
- **Prompt** (`MessageSquareText`): the **Prompt** as the backend recorded it, one bordered block per message in monospace, labelled System prompt, Position, Answer and Retry feedback. The System prompt is folded behind a `Collapsible`, as it is the same every turn. A turn from before prompts were recorded says so.
- **Answer** (`CornerDownLeft`): a Badge with the result and latency ("Legal · 1.2 s", `destructive` unless legal) over the raw reply in monospace on `bg-muted`, its JSON laid out; with no reply, the error.

The tab chosen is kept in this browser across turns, games and reloads. A turn with retries shows "Attempt 2 of 3" between ghost chevron buttons under the tabs, each named (or, at either end, why it is disabled) in its tooltip; it opens on the last attempt, and every tab shows the attempt picked.

It follows the position on the board, live or in the move history: on an LLM's move its turn; on the human's move or the start position, the LLM's last move before it, else a muted "The LLM has not moved yet." ("No LLM has moved yet." in a faceoff). Live after a Forfeit, the Badge is `destructive`, "forfeited". The Thinking appears once the attempt has finished; it is never streamed.

On a Chaos move with a **Legal counterpart** (CONTEXT.md), viewed on its own ply, the panel ends, under a top border, with the counterpart: a muted line with `Scale` and "Legal counterpart", what it is in its tooltip and `aria-description`, then the counterpart's move on a line of its own, numbered as the move list numbers it ("1… e5"). A counterpart that failed shows a muted "none", why in its tooltip. No time and no Stockfish's best move are shown.

## Moves panel

`frontend/src/components/moves/MovesCard.tsx` and `moves.css`, a `Card size="sm"` in the right column:

- **Header**: the title **Moves**, and right-aligned a small Switch, "Show LLM mistakes" ("Show rule-breaking" under Chaos rules), kept in `localStorage` across games.
- **The list**, in a `ScrollArea` on a filled `muted` surface (18px radius) of a set height: 8 rows of 34px with 2px gaps and 6px padding; on a wide window, the height the Moves card leaves it (Layout). No scrollbar shows: the list follows the moves, and the wheel or a swipe still scrolls it. A grid of the move number (13px, muted) and two plies per row, 16px, weight 500, tabular. Each ply is a button with a 10px radius that views the position after it. The latest move is tinted `--move-last`, the move viewed `--move-viewed`; hover is `--accent`. A notation slip has an inset 1px `--slip` line. Under Chaos rules a chaos move is in a muted red (the raw red under Known gap, in Contrast, mixed toward the foreground) and a Spawn in a muted `--spawn`, as the LLM wrote them, at the moves' own weight, with a dotted underline in the same tint; notation slips are not shown (they are still recorded).
- **Mistake chips**, with the switch on, in a row under the move they belong to (these rows come on top of the 8): illegal tries in red with `X` and the move struck through ("Nf7 illegal · try 1"), a forfeit's error in red with `TriangleAlert`, a notation slip in amber with `PenLine` ('written "…"'; not under Chaos rules). 12px, small radius.
- **The LLM mistakes card** ("Rule-breaking" under Chaos rules), with the switch on, a `Card` of its own under the Moves card (`frontend/src/components/moves/MistakesCard.tsx`): the LLM sides **head to head** in a `Table`, White's number on the left, the metric in the middle, Black's on the right; in Play LLM only the LLM's column. The column heads are the side's colour dot and name, the model in the tooltip. A row per metric, its icon and short name with the meaning in the tooltip: illegal tries (`X`; "–" under Enforced decoding, ADR 0003) and notation slips (`PenLine`); under Chaos rules, where an illegal move is played anyway and a slip is no mistake, one row of illegal moves (`X`, illegal tries and chaos moves together) and spawns (`Sparkles`). Numbers 16px tabular; a zero muted; in a faceoff the side with more of a mistake in `destructive` semibold.

Scrolling: to the latest move when live; while a past position is viewed, just enough to keep the move viewed in view (the start position: the top). It scrolls only when a move or a try lands, or the view or the switch changes, so a reader who scrolled up is left there.

There is no Back to live button: → up to the latest move, or clicking it, returns to the live position, and a new move never pulls the view back. Instead the new move **pulses**: an inset 2px `--move-olive` ring, two 0.8s beats, stopping early once the view is back at live; held still under `prefers-reduced-motion`.

## Board

Unchanged by the restyle (`frontend/src/components/board/`): cm-chessboard with the lichess look (`#f0d9b5` / `#b58863` squares, olive last-move tint, green dots, check glow), Merida pieces, the move sound. Its flashes (`flashes.css`: the centre card of an LLM turn's mistakes, the amber slip bubble) and the chaos move's red arrow and the Spawn's purple ring (`board.css`) keep the old page's look. There is no caption under the board.

## Evaluation bar

`frontend/src/components/evaluation-bar/EvaluationBar.tsx` and `evaluation-bar.css`, left of the board at its height, 22px wide, only in an **LLM faceoff** played with an evaluator (never in Play LLM, though the Evaluations are recorded there too). Black's `foreground` from the top, White's `card` from the bottom, a quiet even line at the middle; the fill is White's win chance, `50 + 50 * (2 / (1 + exp(-0.00368208 * centipawns)) - 1)` on the Evaluation capped at ±10, and a mate fills it for the side giving it. Its number, 10px semibold tabular, sits at the leading side's end: "+1.2", "−3.0", "+10.0", "M3" (White mates) or "−M3" (Black mates). It follows the ply viewed in the move history. Focusable, a `role="meter"` named "Evaluation"; its `Tooltip` (on the left; hover and keyboard focus) and `aria-description` hold the details and the engine with its search, e.g. "Stockfish 19 · depth 16, 1 thread, 64 MB hash". The page reads the backend's Evaluations only (`frontend/src/game/evaluation.ts`). Its states:

- **Judged**: the value and its fill.
- **Evaluating**: a ply without an Evaluation yet holds the last judged value, its number breathing.
- **Not judged**: a position that isn't valid chess is greyed at the last judged value, "?" for its number, the reason in the tooltip.
- **Over**: at the last ply of a finished game, the result (1-0, 0-1, ½-½), filled for the winner.
- **Start position**: even, with no number.

## Analytics page

`frontend/src/analytics/AnalyticsPage.tsx`, max 1400px: the top bar with Analytics marked, the title **Leaderboard** (24px semibold) and a muted line under it, then the leaderboard in one `Card`:

- **Header**: the legend of chips and the "All columns" Switch.
- **The table**: its header row is a filled `muted` strip with rounded ends (12px muted labels, the sorted one in foreground with a Lucide arrow); rows are split by faint lines only (`border-border/70`), numbers right-aligned in tabular figures.
- **Chips**: `secondary` Badges in muted text; a chip with a hue (`analytics.css`: one per LLM constraints, green for thinking on) is in the foreground with a coloured dot and a light tint of its hue. The unvalidated Move-quality estimate is a dashed `outline` Badge with a Tooltip.
- **Footer**: the note in muted 12px.

Loading, no games and errors each show in a plain Card in the table's place.

## New game sheet

`frontend/src/settings/NewGameSheet.tsx`, opened by New game in the top bar and ⌘K (Ctrl+K): a `Dialog` (560px, `rounded-4xl`, `shadow-xl`, scrolling within 90% of the window's height) titled **New game**, with the ✕ close button. It sets up the next game and starts it; nothing applies until then.

- **First visit / no game**: when there is no current game (a first visit, or the server restarted), no game starts by itself. The board column shows the board with no pieces, taking no move, without player strips, and the sheet **opens by itself** with the API's defaults for a new game (`GET /api/games/defaults`, the `NewGame` model's defaults in `chessllm/api/app.py`). Closing it leaves the empty board; New game and ⌘K open it again. A reload while a game exists shows that game and leaves the sheet closed.
- **Opening**: always with the last game's settings (`nextGameFrom` in `frontend/src/settings/next-game.ts`, after a Rematch too), or with no game the defaults, Advanced settings closed. Focus goes to the sheet itself, so no tooltip shows until asked for; Tab goes on from there. The models are listed afresh at each opening.
- **Closing**: ✕, Esc or a click outside closes it, leaves the running game as it is and forgets its changes; the next opening starts from the last game again. There is no pending state.
- **Starting** replaces any running game at once, without asking, and closes the sheet: in Play LLM **Play as White** / **Play as Black** (lichess style: the colour is the button; the last game's colour is the primary Button, the other `outline`), each with its side dot; in an LLM faceoff one primary **Start faceoff**.

Top to bottom, every explanation in a Tooltip and the control's `aria-description` (the hover rule):

1. **Mode**: two choice cards, the players as icons above the name: **Play LLM** `User` vs `Bot`, **LLM faceoff** `Bot` vs `Bot`.
2. **Opponent**: Play LLM, one model `Select`; LLM faceoff, White's and Black's model, each under its side's dot and name, with an `outline` icon Button (`ArrowLeftRight`, "Swap colours") between them that swaps the LLMs with their settings. If the models can't be listed, a `text-destructive` alert line says why and the chosen models stay.
3. **Thinking**: a row with its name and a `Switch`, "Reasons before each move. Slower, likely stronger."; disabled when the model can't think, the tooltip naming it ("llama3:8b can't think."; in a faceoff each model that can't).
4. **Rules**: two choice cards, **Standard** `ChessKnight` and **Chaos** `Zap`. Under an enforced constraint Chaos is disabled (40% opacity), its tooltip giving the reason ("Needs an LLM that can play an illegal move: pick Board only or Board + legal moves in Advanced settings.", naming the side when customized per LLM). Under Chaos rules a **Legal counterpart** switch follows, on by default, what it costs in its tooltip; it is not part of the Player configuration.
5. **Advanced settings**: a `Collapsible` on a light `muted` surface (`rounded-3xl`), closed by default, its trigger a `ChevronDown` (turned while closed) and the name, its summary "What the LLM sees, retries, forfeit" as the tooltip. Inside:
   - **What the LLM is given**: the four LLM constraints as cards with the Game card's icons, the plain name with the glossary term under it in muted 12px: Board only (Free), Board + legal moves (Listed), Kept legal, not told (Blind enforced), Shown and kept legal (Listed enforced).
   - **After an illegal move, tell the LLM**: Retry feedback as four cards, two by two, Explained / Bare / Hinted / Repeat.
   - **Illegal moves before forfeit**: a `Select` of 1 to 25, default 5, the tooltip counting the retries it leaves.
   - Retry feedback is hidden (not disabled) for an LLM under an enforced constraint, the forfeit limit when every LLM is (ADR 0003).
   - **Customize per LLM** (faceoff only): a switch row; on, a `card` block per side (its dot, side and model) with that LLM's Thinking, constraints and Retry feedback, and the shared Thinking row above goes.
6. The start button(s).

Choice cards are a `Radio group` of filled cards (`rounded-2xl bg-muted`, hover `accent`; chosen: `card` with a 2px primary ring), the 20px icon (stroke 1.75) above the name. The words (names and meanings of the constraints, Rules and Retry feedback) are the Game card's, from `frontend/src/game/wording.ts`. No summary line (the Game card shows the running game's Rules, and the settings its LLMs differ in), no presets, no sampling table (`chessllm/llm/sampling.toml` is where sampling is set) and no Move sound (it is in Preferences).

## Patterns this replaced

The React port (#29) carried the old page's generic look. These are gone; don't bring them back.

| Replaced | With |
| --- | --- |
| Stock shadcn neutral theme, whose secondary text fails AA on a grey page | The Stone palette, warm greys with a darker muted foreground, checked by tests |
| Every block in a bordered card | Luma cards set off by fill and shadow; inside them filled `muted` surfaces, and faint lines only between table rows |
| Glyph icons (♞ ⚙ ✦ ⚑ …) | Lucide icons; the Merida rook as the mark and tab icon; Merida pieces for captures |
| The Settings modal, its sections, description lines, sampling table and "changes apply to the next game" note | The New game sheet, which starts the game it sets up |
| A row of setting chips in the top bar | The settings in the Game card: the Rules as an icon, the rest as text, each explained in its tooltip |
| Uppercase micro-labels | Sentence-case `CardTitle`s and muted text |
| Status sentences ("Black · qwen3.5:9b is thinking… 12s", "Your move", "Waiting for…") | The turn ring and the move timer in the player strips |
| The result banner | The result line and Rematch in the Game card |
| Players shown only as chips | Player strips with logo, name, captures, spawns and +N |
| A move list that grows with the game, and Back to live | A fixed-height list of 8 rows that scrolls itself, and the pulse on a new move |
| "Show thinking" and "Show prompt" switches | The Turn panel's tabs, the last one chosen remembered |
