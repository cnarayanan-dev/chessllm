"""The Ranking: the models in order of their Rating under the Reference configuration, each with its Move-quality
estimate and record (ADR 0011). It ranks models, never Player configurations.

Only games in which every LLM side plays under the Reference configuration count, so a game under any other settings
is left out of every number, the Rating's fit included. Narrowed to some Modes, every number comes from those Modes'
games alone: the Rating is fitted afresh from them, so LLM faceoffs alone reach no Anchor and give no Rating, and Play
LLM games never give one (ADR 0005). Read from the logs on every request, like the leaderboard."""

from collections import defaultdict
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Literal, get_args

from pydantic import BaseModel

from chessllm.analytics.analysis import analysis_path
from chessllm.analytics.leaderboard import (
    PlayerConfiguration,
    Tally,
    finished_game,
    llm_configuration,
    logged_mode,
    rated_game,
    read_sides,
    side_outcome,
)
from chessllm.analytics.move_quality import (
    ConfigurationMoves,
    MoveQuality,
    move_quality,
    read_analysed_moves,
    read_validation,
)
from chessllm.analytics.rating import RatedGame, Rating, ratings
from chessllm.core.config import VALIDATION_FILE
from chessllm.core.types import ModeKey
from chessllm.engines.anchors import ANCHOR_RATINGS, AnchorRating
from chessllm.game.llm_turn.prompt import default_template, prompt_file

ALL_MODES: tuple[ModeKey, ...] = get_args(ModeKey)


def reference_configuration(model: str) -> PlayerConfiguration:
    """The Reference configuration for the model: thinking off, Free, Standard rules, 5 attempts per turn with
    explained Retry feedback, fresh Turn memory, no Tools, the default Prompt template and the model's own sampling
    (no sampling options set). Changed only by a new ADR (ADR 0011)."""
    default = prompt_file(default_template("free", "default"), "free")
    assert default is not None
    return PlayerConfiguration(
        model=model,
        thinking=False,
        llm_constraints="free",
        rules="standard",
        retry_feedback="explained",
        max_retries=4,
        sampling={},
        prompt=default.name,
        position=None,
        turn_memory=None,
        thinking_level=None,
        thinking_budget=None,
        tools=(),
        tool_call_cap=None,
    )


def is_reference(configuration: PlayerConfiguration) -> bool:
    """Whether the configuration is the Reference configuration, its model aside."""
    return configuration == reference_configuration(configuration.model)


# Why a model has no Rating: no games under the Reference configuration (in the chosen Modes), only Play LLM games,
# which never give one, or no path from its games to an Anchor.
NoRating = Literal["no_reference_games", "no_rated_games", "no_path_to_anchor"]


class RankingEntry(BaseModel):
    """One model, from its games under the Reference configuration in the chosen Modes. A game it played on both
    sides of an LLM faceoff counts once for each side."""

    rank: int | None  # 1 for the highest Rating; None without a Rating
    model: str
    rating: Rating | None  # never blended with the Move-quality estimate (ADR 0005)
    no_rating: NoRating | None  # why there is no Rating; None when there is one
    move_quality: MoveQuality | None  # pooled from the analysis files of its games, Play LLM included
    games: int
    wins: int
    draws: int
    losses: int
    forfeits: int  # games lost by Forfeit, among the losses


class Ranking(BaseModel):
    modes: list[ModeKey]  # the Modes whose games it comes from, in the Modes' order
    models: list[RankingEntry]  # ranked by Rating, then the models without one by name


# An upper bound sorts below every estimate: "< 300" may be far lower than an estimate of 120.
UPPER_BOUND = -1_000_000


def rating_key(rating: Rating) -> int:
    """The number a Rating ranks by: its estimate, a lower bound's number, an upper bound below all of those."""
    if rating.estimate is not None:
        return rating.estimate
    if rating.low is not None:
        return rating.low
    assert rating.high is not None
    return UPPER_BOUND + rating.high


def ranking(
    games_dir: Path,
    modes: Collection[ModeKey] = ALL_MODES,
    move_quality_validation: Path = VALIDATION_FILE,
    anchors: Mapping[str, AnchorRating] = ANCHOR_RATINGS,
) -> Ranking:
    models: set[str] = set()  # every model an LLM side played, under any settings and in any Mode
    tallies: dict[str, Tally] = defaultdict(Tally)
    forfeits: dict[str, int] = defaultdict(int)
    analysed: dict[str, ConfigurationMoves] = defaultdict(ConfigurationMoves)
    rated: list[RatedGame] = []
    rated_models: set[str] = set()  # the models with a game the Rating counts, whatever its result
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
        if logged_mode(start) not in modes or not all(map(is_reference, configurations.values())):
            continue
        analysed_sides = read_analysed_moves(analysis_path(path))
        for color, configuration in configurations.items():
            outcome = side_outcome(end["result"], color)
            tallies[configuration.model].add(outcome)
            forfeits[configuration.model] += outcome == "loss" and end["reason"] == "forfeit"
            if color in analysed_sides:
                analysed[configuration.model].add(*analysed_sides[color])
        if game := rated_game(events):
            rated.extend(game)
            rated_models.update(configuration.model for configuration in configurations.values())
    fitted = ratings(rated, anchors)
    validated_for = read_validation(move_quality_validation)

    def no_rating(model: str, games: int) -> NoRating:
        if games == 0:
            return "no_reference_games"
        return "no_path_to_anchor" if model in rated_models else "no_rated_games"

    def entry(model: str) -> RankingEntry:
        tally = tallies.get(model, Tally())
        rating = fitted.get(reference_configuration(model).id())
        return RankingEntry(
            rank=None,
            model=model,
            rating=rating,
            no_rating=None if rating is not None else no_rating(model, tally.games),
            move_quality=move_quality(analysed[model], validated_for),
            games=tally.games,
            wins=tally.wins,
            draws=tally.draws,
            losses=tally.losses,
            forfeits=forfeits.get(model, 0),
        )

    entries = [entry(model) for model in sorted(models)]
    ranked = sorted(
        (entry for entry in entries if entry.rating is not None),
        key=lambda entry: -rating_key(entry.rating),  # type: ignore[arg-type]  # only entries with a Rating
    )
    for rank, ranked_entry in enumerate(ranked, start=1):
        ranked_entry.rank = rank
    # Then the models with games but no Rating, then those without games under the Reference configuration, each
    # by name: the sorts are stable.
    unranked = sorted((entry for entry in entries if entry.rating is None), key=lambda entry: entry.games == 0)
    return Ranking(modes=[mode for mode in ALL_MODES if mode in modes], models=[*ranked, *unranked])
