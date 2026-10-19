// The Reasoning panel, under the Game card: the Reasoning (CONTEXT.md) of the LLM move on the board.
import type { GameState, LlmTurn } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { COLOR_NAMES, faceoff } from '@/game/wording'

type ReasoningPanelProps = {
  game: GameState
  /** The ply the position on the board follows (0: the start position). */
  ply: number
  /** Whether the board shows the game as it is, rather than a past position in the move history. */
  live: boolean
}

/**
 * The LLM turn that goes with the position after `ply`: the LLM's move there, or its last move before it. Live after
 * a Forfeit, the forfeited turn, which has no ply of its own.
 */
function turnShown(game: GameState, ply: number, live: boolean): LlmTurn | null {
  const upTo = live && game.end_reason === 'forfeit' ? game.plies.length + 1 : ply
  return game.llm_turns.findLast((turn) => turn.ply <= upTo) ?? null
}

/** The turn's move as the move list numbers it, e.g. "10… Nxa1", or "forfeited" for a turn that played none. */
function moveName(game: GameState, turn: LlmTurn): string {
  const ply = game.plies[turn.ply - 1]
  return ply ? `${Math.ceil(turn.ply / 2)}${turn.color === 'white' ? '.' : '…'} ${ply.written}` : 'forfeited'
}

/** The LLM as the heading names it: the model, and in a faceoff its side first, e.g. "White · gemma3:4b". */
function headingName(game: GameState, turn: LlmTurn): string {
  const side = game.settings[turn.color]
  const model = side.player === 'llm' ? side.model : ''
  return faceoff(game) ? `${COLOR_NAMES[turn.color]} · ${model}` : model
}

/**
 * The turn's Reasoning, which is its last attempt's: the one that was played, or after a Forfeit the last one tried.
 * Else why there is none, as a quiet line: thinking on, which gives none, or a last attempt with no answer.
 */
function reasoningOf(game: GameState, turn: LlmTurn): { text: string; quiet: boolean } {
  const side = game.settings[turn.color]
  if (side.player === 'llm' && side.thinking) {
    return { text: `${side.model} plays with thinking on, so it gives no Reasoning.`, quiet: true }
  }
  if (turn.reasoning) return { text: turn.reasoning, quiet: false }
  const why = turn.attempts.at(-1)?.error ? 'It gave no answer, so there is no Reasoning.' : 'Its reply has no Reasoning.'
  return { text: why, quiet: true }
}

export function ReasoningPanel({ game, ply, live }: ReasoningPanelProps) {
  const turn = turnShown(game, ply, live)
  const move = turn && moveName(game, turn)
  const reasoning = turn && reasoningOf(game, turn)
  return (
    <Card role="region" aria-label="Reasoning" className="text-[15px]">
      <CardHeader className="flex flex-wrap items-center gap-2">
        <CardTitle className="font-semibold">Reasoning</CardTitle>
        {turn && (
          <Badge
            variant={move === 'forfeited' ? 'destructive' : 'secondary'}
            className="h-auto max-w-full py-1 whitespace-normal"
            data-testid="reasoning-move"
          >
            {`${headingName(game, turn)} · ${move}`}
          </Badge>
        )}
      </CardHeader>
      <CardContent>
        {reasoning ? (
          <p
            className={
              reasoning.quiet
                ? 'text-sm text-muted-foreground'
                : 'leading-relaxed whitespace-pre-wrap text-card-foreground'
            }
          >
            {reasoning.text}
          </p>
        ) : (
          <p className="text-sm text-muted-foreground">
            {faceoff(game) ? 'No LLM has moved yet.' : 'The LLM has not moved yet.'}
          </p>
        )}
      </CardContent>
    </Card>
  )
}
