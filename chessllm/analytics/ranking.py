"""The Ranking: every model in order of its Rating under the Reference configuration (ADR 0011), with its
Move-quality estimate and its record, from its games under the Reference configuration alone.

Read from the game logs on every request, as the leaderboard is. A game counts only if every LLM side in it plays
the Reference configuration: a faceoff against another configuration of any model is left out entirely, from the
record as from the fit, since what places that configuration is outside the Ranking. Narrowed to some Modes, every
number is recomputed from those games alone, the Rating fitted from that subset of the pool: LLM faceoffs alone reach
no Anchor, and Play LLM games never give a Rating (ADR 0005)."""

from collections import defaultdict
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Literal, get_args

from pydantic import BaseModel

from chessllm.analytics.leaderboard import (
    PlayerConfiguration,
    Tally,
    add_analysed_moves,
    finished_game,
    llm_configuration,
    rated_game,
    read_sides,
    side_outcome,
)
from chessllm.analytics.move_quality import (
    ConfigurationMoves,
    MoveQuality,
    move_quality,
    read_validation,
)
from chessllm.analytics.rating import RatedGame, Rating, counted, ratings
from chessllm.core.config import VALIDATION_FILE
from chessllm.core.types import ModeKey
from chessllm.engines.anchors import ANCHOR_RATINGS, AnchorRating
from chessllm.game.llm_turn.prompt import SYSTEM_PROMPT_FILES

# The settings every model is ranked under, everything in a Player configuration but the model (ADR 0011): thinking
# off with no Thinking level or budget, Free, Standard rules, 5 attempts with explained Retry feedback, fresh Turn
# memory, no Tools, the default Prompt template and the model's own sampling. The command-line defaults, so a default
# Anchor match batch plays under it. The default Prompt template is matched as games are grouped, by its System
# prompt file (prompt_settings), not by its ID, whose version changes with every edit of the file: a game played on
# an earlier text of the default still counts, and a Prompt lab template never does. Changed only by a new ADR.
REFERENCE_CONFIGURATION = PlayerConfiguration(
    model="",
    thinking=False,
    llm_constraints="free",
    rules="standard",
    retry_feedback="explained",
    max_retries=4,  # 5 attempts
    sampling={},
    prompt=SYSTEM_PROMPT_FILES["free"].name,
    position=None,  # fen
    turn_memory=None,  # fresh
    thinking_level=None,
    thinking_budget=None,
    tools=None,
    tool_call_cap=None,
)

ALL_MODES: tuple[ModeKey, ...] = get_args(ModeKey)


def reference_configuration(model: str) -> PlayerConfiguration:
    """The model's Player configuration under the Reference configuration."""
    return REFERENCE_CONFIGURATION.model_copy(update={"model": model})


def is_reference(configuration: PlayerConfiguration) -> bool:
    """Whether the configuration is the Reference configuration: it matches it with only the model differing.
    Compared by id, as games are grouped and Ratings looked up, so a setting logged at its default (position fen,
    Turn memory fresh) is the same as one left out."""
    return configuration.id() == reference_configuration(configuration.model).id()


# Why a model has no Rating:
# - no_reference_games: no games under the Reference configuration (in the Modes asked for)
# - play_llm_only: only Play LLM games, which never give one
# - no_rated_opponent: its Anchor matches and LLM faceoffs were all against itself or an Anchor of unknown strength,
#   which say nothing about the scale
# - no_anchor_path: its LLM faceoffs don't lead to an Anchor in the direction of their results (faceoffs only)
NoRating = Literal["no_reference_games", "play_llm_only", "no_rated_opponent", "no_anchor_path"]


class RankingEntry(BaseModel):
    """One model's place in the Ranking, from its games under the Reference configuration in the Modes asked for. A
    game it played on both sides of an LLM faceoff counts once for each side."""

    model: str
    rank: int | None  # 1 for the highest Rating; None without a Rating, listed after every ranked model
    # Fitted from Anchor matches and LLM faceoffs alone, a Forfeit a loss: an estimate, or an upper or lower bound
    rating: Rating | None
    no_rating: NoRating | None  # why rating is None; None when it has one
    # Pooled from the analysis files of the same games, Play LLM included; never blended with the Rating (ADR 0005)
    move_quality: MoveQuality | None
    games: int
    wins: int
    draws: int
    losses: int
    forfeits: int  # games lost by Forfeit, among the losses


class Ranking(BaseModel):
    modes: list[ModeKey]  # the Modes whose games it counts, in the order of ModeKey
    models: list[RankingEntry]  # ranked first, by Rating; then the unranked, those with reference games first


def ranking(
    games_dir: Path,
    modes: Collection[ModeKey] = ALL_MODES,
    move_quality_validation: Path = VALIDATION_FILE,
    anchors: Mapping[str, AnchorRating] = ANCHOR_RATINGS,
) -> Ranking:
    """The Ranking of every model with a finished game under any settings, counting only the games under the
    Reference configuration in the given Modes (all when empty)."""
    chosen = [mode for mode in ALL_MODES if mode in modes] or list(ALL_MODES)
    tallies: dict[str, Tally] = defaultdict(Tally)
    forfeits: dict[str, int] = defaultdict(int)
    analysed: dict[str, ConfigurationMoves] = defaultdict(ConfigurationMoves)
    rated: list[RatedGame] = []
    models: set[str] = set()
    for path in sorted(games_dir.glob("*.jsonl")):
        events = finished_game(path)
        if events is None:
            continue
        start, end = events[0], events[-1]
        sides, _ = read_sides(start, end)
        configurations = {
            color: llm_configuration(start, color, side) for color, side in sides.items() if side["player"] == "llm"
        }
        models.update(configuration.model for configuration in configurations.values())
        mode = start.get("mode") if "log_version" in start else "play_llm"  # version 1 logs are all Play LLM
        if mode not in chosen or not all(map(is_reference, configurations.values())):
            continue
        for color, configuration in configurations.items():
            outcome = side_outcome(end["result"], color)
            tallies[configuration.model].add(outcome)
            forfeits[configuration.model] += outcome == "loss" and end["reason"] == "forfeit"
        add_analysed_moves(analysed, path, events)  # by configuration id
        rated.extend(rated_game(events))

    fitted = ratings(rated, anchors)
    validated_for = read_validation(move_quality_validation)
    played_rated = {player for game in rated for player in (game.white, game.black)}
    in_pool = {player for game in rated if counted(game, anchors) for player in (game.white, game.black)}
    entries = []
    for model in models:
        key = reference_configuration(model).id()
        tally, rating = tallies.get(model, Tally()), fitted.get(key)
        no_rating: NoRating | None = None
        if rating is None and not tally.games:
            no_rating = "no_reference_games"
        elif rating is None and key not in played_rated:
            no_rating = "play_llm_only"
        elif rating is None:
            no_rating = "no_anchor_path" if key in in_pool else "no_rated_opponent"
        quality = move_quality(analysed[key], validated_for) if key in analysed else None
        entries.append(
            RankingEntry(
                model=model,
                rank=None,
                rating=rating,
                no_rating=no_rating,
                move_quality=quality,
                games=tally.games,
                wins=tally.wins,
                draws=tally.draws,
                losses=tally.losses,
                forfeits=forfeits.get(model, 0),
            )
        )
    entries.sort(key=order)
    for number, entry in enumerate(entry for entry in entries if entry.rating is not None):
        entry.rank = number + 1
    return Ranking(modes=chosen, models=entries)


def order(entry: RankingEntry) -> tuple[int, float, str]:
    """Rated models first, highest Rating first: an estimate, or a lower bound's number, and an upper bound below
    every estimate ("< 300" may be far lower than an estimate of 120). Then the models with reference games but no
    Rating, then those without; within each, by model."""
    rating = entry.rating
    if rating is None:
        return (1 if entry.games else 2), 0.0, entry.model
    if rating.estimate is not None:
        return 0, -rating.estimate, entry.model
    if rating.low is not None:
        return 0, -rating.low, entry.model
    return 0, 1_000_000 - (rating.high or 0), entry.model
