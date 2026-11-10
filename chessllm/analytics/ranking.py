"""The Ranking: the models in order of their Rating under the Reference configuration, each with its Move-quality
estimate and record (ADR 0011). It ranks models, never Player configurations. LLMs and System 1 models are ranked
together, each entry saying which kind it is (ADR 0012).

Only games in which every model side plays under the Reference configuration count, so a game under any other settings
is left out of every number, the Rating's fit included. Narrowed to some Modes, every number comes from those Modes'
games alone: the Rating is fitted afresh from them, so LLM faceoffs alone reach no Anchor and give no Rating, and Play
LLM games never give one (ADR 0005). Read from the logs on every request, like the leaderboard."""

from collections import defaultdict
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Literal, get_args, overload

from pydantic import BaseModel, Field

from chessllm.analytics.analysis import analysis_path
from chessllm.analytics.leaderboard import (
    ModelConfiguration,
    ModelKind,
    PlayerConfiguration,
    System1Configuration,
    Tally,
    finished_game,
    logged_mode,
    model_configurations,
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
from chessllm.game.llm_turn.prompt import default_template, prompt_file, text_version
from chessllm.llm.models import is_hosted
from chessllm.system1.prompt import DEFAULT_TEMPLATE as DEFAULT_SYSTEM1_TEMPLATE

ALL_MODES: tuple[ModeKey, ...] = get_args(ModeKey)


@overload
def reference_configuration(model: str, kind: Literal["llm"] = "llm") -> PlayerConfiguration: ...
@overload
def reference_configuration(model: str, kind: Literal["system1"]) -> System1Configuration: ...
@overload
def reference_configuration(model: str, kind: ModelKind) -> ModelConfiguration: ...
def reference_configuration(model: str, kind: ModelKind = "llm") -> ModelConfiguration:
    """The Reference configuration for the model: for an LLM thinking off, Free, Standard rules, 5 attempts per turn
    with explained Retry feedback, fresh Turn memory, no Tools, the default Prompt template and the model's own
    sampling (no sampling options set); for a System 1 model only what applies to it: Standard rules, its default
    Prompt template and a Choice temperature of 1. Changed only by a new ADR (ADR 0011, ADR 0012)."""
    if kind == "system1":
        return System1Configuration(
            model=model,
            rules="standard",
            choice_temperature=1.0,
            prompt_template=text_version(
                DEFAULT_SYSTEM1_TEMPLATE.system_prompt, DEFAULT_SYSTEM1_TEMPLATE.turn_template
            ),
        )
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


# A model is told apart by its kind as well as its name: an LLM and a System 1 model of one name are two models.
ModelKey = tuple[ModelKind, str]


def model_key(configuration: ModelConfiguration) -> ModelKey:
    return configuration.kind, configuration.model


def is_reference(configuration: ModelConfiguration) -> bool:
    """Whether the configuration is the Reference configuration, its model aside."""
    return configuration == reference_configuration(configuration.model, configuration.kind)


# Why a model has no Rating: no games under the Reference configuration (in the chosen Modes), only Play LLM games,
# which never give one, or no path from its games to an Anchor.
NoRating = Literal["no_reference_games", "no_rated_games", "no_path_to_anchor"]


class RankingEntry(BaseModel):
    """One model, from its games under the Reference configuration in the chosen Modes. A game it played on both
    sides of an LLM faceoff counts once for each side."""

    rank: int | None  # 1 for the highest Rating; None without a Rating
    model: str
    kind: ModelKind  # an LLM or a System 1 model; a model of each kind with one name is two entries
    # Whether it is a Hosted model (ADR 0013), an LLM that runs on a provider's servers; left out for any other
    hosted: bool | None = Field(default=None, exclude_if=lambda hosted: not hosted)
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
    models: set[ModelKey] = set()  # every model a side played, under any settings and in any Mode
    tallies: dict[ModelKey, Tally] = defaultdict(Tally)
    forfeits: dict[ModelKey, int] = defaultdict(int)
    analysed: dict[ModelKey, ConfigurationMoves] = defaultdict(ConfigurationMoves)
    rated: list[RatedGame] = []
    rated_models: set[ModelKey] = set()  # the models with a game the Rating counts, whatever its result
    for path in sorted(games_dir.glob("*.jsonl")):
        events = finished_game(path)
        if events is None:
            continue
        start, end = events[0], events[-1]
        sides, _ = read_sides(start, end)
        configurations = model_configurations(start, sides)
        models.update(model_key(configuration) for configuration in configurations.values())
        if logged_mode(start) not in modes or not all(map(is_reference, configurations.values())):
            continue
        analysed_sides = read_analysed_moves(analysis_path(path))
        for color, configuration in configurations.items():
            outcome = side_outcome(end["result"], color)
            key = model_key(configuration)
            tallies[key].add(outcome)
            forfeits[key] += outcome == "loss" and end["reason"] == "forfeit"
            if color in analysed_sides:
                analysed[key].add(*analysed_sides[color])
        if game := rated_game(events):
            rated.extend(game)
            rated_models.update(model_key(configuration) for configuration in configurations.values())
    fitted = ratings(rated, anchors)
    validated_for = read_validation(move_quality_validation)

    def no_rating(key: ModelKey, games: int) -> NoRating:
        if games == 0:
            return "no_reference_games"
        return "no_path_to_anchor" if key in rated_models else "no_rated_games"

    def entry(key: ModelKey) -> RankingEntry:
        kind, model = key
        tally = tallies.get(key, Tally())
        rating = fitted.get(reference_configuration(model, kind).id())
        return RankingEntry(
            rank=None,
            model=model,
            kind=kind,
            hosted=kind == "llm" and is_hosted(model),
            rating=rating,
            no_rating=None if rating is not None else no_rating(key, tally.games),
            move_quality=move_quality(analysed[key], validated_for),
            games=tally.games,
            wins=tally.wins,
            draws=tally.draws,
            losses=tally.losses,
            forfeits=forfeits.get(key, 0),
        )

    entries = [entry(key) for key in sorted(models, key=lambda key: key[::-1])]  # by name, then kind
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
