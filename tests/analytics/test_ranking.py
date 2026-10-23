"""The Ranking: models, each by its Rating under the Reference configuration (ADR 0011), with its Move-quality
estimate and its record from those games alone, narrowed by Mode when asked."""

import json

import pytest
from fastapi.testclient import TestClient

from chessllm.analytics.leaderboard import (
    PlayerConfiguration,
    llm_configuration,
    settings_configuration,
)
from chessllm.analytics.ranking import (
    REFERENCE_CONFIGURATION,
    is_reference,
    reference_configuration,
)
from chessllm.api.app import create_app
from chessllm.cli.anchor_batch import parser
from chessllm.cli.common import anchor_match_settings
from chessllm.core.config import SAMPLING_FILE
from tests.analytics.test_leaderboard import HUMAN, LLAMA, game, with_start, write_log
from tests.analytics.test_leaderboard_move_quality import analysis
from tests.analytics.test_leaderboard_rating import against_anchor, faceoffs

QWEN = LLAMA | {"model": "qwen3.5:9b"}
GEMMA = LLAMA | {"model": "gemma3:12b"}
MISTRAL = LLAMA | {"model": "mistral:7b"}


def reference(*games):
    """The games with 5 attempts a turn, the Reference configuration's (the helpers log 4, as max_retries 3)."""
    return [with_start(events, max_retries=4) for events in games]


@pytest.fixture
def ranking(tmp_path):
    """Writes (game log, analysis file or None) pairs, or bare game logs, into a temporary games directory and
    returns the Ranking the API makes of them, narrowed to the Modes given."""

    def make(*games, modes=()) -> list[dict]:
        games_dir = tmp_path / "games"
        for path in games_dir.glob("*") if games_dir.exists() else []:
            path.unlink()
        for number, given in enumerate(games):
            events, analysed = given if isinstance(given, tuple) else (given, None)
            name = f"2026-10-19T10-00-{number:03d}_game"
            write_log(games_dir, name, events)
            if analysed is not None:
                (games_dir / f"{name}.analysis.json").write_text(json.dumps(analysed), encoding="utf-8")
        games_dir.mkdir(parents=True, exist_ok=True)
        client = TestClient(create_app(lambda settings, color: None, games_dir=games_dir))
        response = client.get("/api/ranking", params={"mode": list(modes)})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["modes"] == (list(modes) or ["play_llm", "llm_faceoff", "anchor_match"])
        return body["models"]

    return make


def by_model(models):
    return {entry["model"]: entry for entry in models}


def record(entry):
    return entry["games"], entry["wins"], entry["draws"], entry["losses"], entry["forfeits"]


# The Reference configuration


def test_the_reference_configuration_is_the_default_anchor_match_batchs():
    """A default Anchor match batch plays under it, so the batches the benchmark runs by default count."""
    args = parser().parse_args(["--model", "llama3:8b"])
    settings = anchor_match_settings(args, "white", 1, SAMPLING_FILE)  # the shipped one, every option unset

    assert settings_configuration(settings, "white") == reference_configuration("llama3:8b")
    assert reference_configuration("llama3:8b").model_dump() == {
        "model": "llama3:8b",
        "thinking": False,
        "llm_constraints": "free",
        "rules": "standard",
        "retry_feedback": "explained",
        "max_retries": 4,
        "sampling": {},
        "prompt": "system.txt",
    }
    assert REFERENCE_CONFIGURATION.model == ""  # every model's is this one, with its own model


@pytest.mark.parametrize(
    "change",
    [
        {"thinking": True},
        {"thinking": True, "thinking_level": "low"},
        {"thinking": True, "thinking_budget": 2048},
        {"llm_constraints": "listed"},
        {"llm_constraints": "listed_enforced"},
        {"rules": "chaos"},
        {"retry_feedback": "bare"},
        {"max_retries": 3},
        {"sampling": {"temperature": 0.7}},
        {"prompt": "my-template@1f0c2a9e"},
        {"position": "described"},
        {"turn_memory": "chat_position"},
        {"tools": ("legal_moves",), "tool_call_cap": 8},
    ],
    ids=lambda change: next(iter(change)) if len(change) == 1 else "+".join(change),
)
def test_a_configuration_differing_in_any_setting_but_the_model_is_not_the_reference(change):
    configuration = reference_configuration("gemma3:12b")

    assert is_reference(configuration)
    assert not is_reference(PlayerConfiguration(**configuration.model_dump() | change))


def test_the_default_prompt_template_counts_whatever_its_version():
    """The default Prompt template is matched by its System prompt file, as games are grouped, so a game played
    on an earlier text of the default still counts; a Prompt lab template is never the default, even if named so."""
    played = with_start(game(HUMAN, LLAMA, "1-0"), max_retries=4)[0]
    side = LLAMA | {"prompt_template": {"id": "default@00000000"}}
    from_the_lab = {key: value for key, value in played.items() if key != "prompt_file"}  # no file holds it

    assert is_reference(llm_configuration(played, "black", side))
    assert not is_reference(llm_configuration(from_the_lab, "black", side))


# The Ranking


def test_one_entry_per_model_from_its_reference_games_only(ranking):
    models = by_model(
        ranking(
            *reference(*against_anchor(LLAMA, 1, wins=5, draws=1, losses=2, forfeits=2)),
            *reference(*against_anchor(LLAMA | {"llm_constraints": "listed"}, 1, wins=10)),
            *against_anchor(LLAMA, 1, wins=10),  # 4 attempts a turn
        )
    )

    assert list(models) == ["llama3:8b"]
    llama = models["llama3:8b"]
    assert record(llama) == (10, 5, 1, 4, 2)
    assert llama["rank"] == 1
    assert llama["rating"]["rated_games"] == 10
    assert llama["no_rating"] is None


@pytest.mark.parametrize(
    "other",
    [
        {"rules": "chaos"},
        {"side": {"llm_constraints": "listed_enforced"}},
        {"side": {"thinking": True}},
        {"side": {"retry_feedback": "hinted"}},
        {"sampling": {"temperature": 0.2}},
    ],
    ids=["chaos", "listed_enforced", "thinking", "retry_feedback", "sampling"],
)
def test_a_model_with_games_under_other_settings_only_is_listed_last_unranked(ranking, other):
    side = LLAMA | other.get("side", {})
    other_games = [
        with_start(events, **({"sampling": other["sampling"]} if "sampling" in other else {}))
        for events in reference(*against_anchor(side, 1, wins=6, losses=4, rules=other.get("rules")))
    ]

    models = ranking(*reference(*against_anchor(QWEN, 1, losses=5)), *other_games)

    assert [entry["model"] for entry in models] == ["qwen3.5:9b", "llama3:8b"]
    llama = models[1]
    assert record(llama) == (0, 0, 0, 0, 0)
    assert (llama["rank"], llama["rating"], llama["move_quality"]) == (None, None, None)
    assert llama["no_rating"] == "no_reference_games"


def test_the_rating_is_fitted_from_reference_games_alone(ranking):
    """LLAMA beat QWEN under the reference, but QWEN met an Anchor only with thinking on: no path to an Anchor."""
    qwen_thinking = QWEN | {"thinking": True}
    models = by_model(
        ranking(
            *reference(*faceoffs(LLAMA, QWEN, wins=6, losses=2)),
            *reference(*against_anchor(qwen_thinking, 3, wins=5, losses=5)),
            *reference(*faceoffs(LLAMA, qwen_thinking, wins=3)),  # a faceoff against another configuration
        )
    )

    llama, qwen = models["llama3:8b"], models["qwen3.5:9b"]
    assert (llama["rating"], qwen["rating"]) == (None, None)
    assert llama["no_rating"] == qwen["no_rating"] == "no_anchor_path"
    assert record(llama) == (8, 6, 0, 2, 0)  # without the faceoff against qwen with thinking on
    assert record(qwen) == (8, 2, 0, 6, 0)


def test_faceoffs_under_the_reference_place_a_model_that_never_met_an_anchor(ranking):
    models = ranking(
        *reference(*against_anchor(QWEN, 3, wins=5, losses=5)),
        *reference(*faceoffs(LLAMA, QWEN, wins=7, losses=3)),
        *reference(*faceoffs(GEMMA, QWEN, losses=8)),
        *reference(*[game(HUMAN, MISTRAL, "1-0") for _ in range(3)]),
    )

    assert [(entry["rank"], entry["model"]) for entry in models] == [
        (1, "llama3:8b"),
        (2, "qwen3.5:9b"),
        (3, "gemma3:12b"),  # "< X", below every estimate
        (None, "mistral:7b"),  # Play LLM only: no Rating, but a record
    ]
    gemma, mistral = models[2], models[3]
    assert (gemma["rating"]["estimate"], gemma["no_rating"]) == (None, None)
    assert gemma["rating"]["high"] is not None
    assert mistral["no_rating"] == "play_llm_only"
    assert record(mistral) == (3, 0, 0, 3, 0)


def test_a_faceoff_of_a_model_with_itself_counts_for_both_sides(ranking):
    [llama] = ranking(*reference(game(LLAMA, LLAMA, "1-0"), game(LLAMA, LLAMA, "1/2-1/2", "move_cap")))

    assert record(llama) == (4, 1, 2, 1, 0)
    assert llama["no_rating"] == "no_rated_opponent"  # games against itself say nothing about the scale


def test_games_against_an_anchor_of_unknown_strength_give_no_rating_and_say_so(ranking):
    unknown = {"player": "anchor", "engine": "dragon", "skill": 9}
    [llama] = ranking(*reference(game(LLAMA, unknown, "1-0", mode="anchor_match")))

    assert (llama["rating"], llama["no_rating"]) == (None, "no_rated_opponent")
    assert record(llama) == (1, 1, 0, 0, 0)


def test_a_side_logged_with_its_settings_at_their_defaults_plays_the_reference(ranking):
    """A log that names the default position and Turn memory is the same configuration as one that leaves them out."""
    explicit = LLAMA | {"position": "fen", "turn_memory": "fresh"}
    configuration = PlayerConfiguration(**reference_configuration("llama3:8b").model_dump(), position="fen")

    [llama] = ranking(*reference(*against_anchor(explicit, 1, wins=3, losses=3), *against_anchor(LLAMA, 1, wins=2)))

    assert is_reference(configuration)
    assert record(llama) == (8, 5, 0, 3, 0)
    assert llama["rating"]["rated_games"] == 8


MIXED = [
    *reference(*against_anchor(QWEN, 3, wins=5, losses=5)),
    *reference(*faceoffs(LLAMA, QWEN, wins=7, losses=3)),
    *reference(*[game(HUMAN, LLAMA, "0-1") for _ in range(4)]),
]


def test_llm_faceoffs_alone_give_no_rating(ranking):
    models = by_model(ranking(*MIXED, modes=["llm_faceoff"]))

    llama, qwen = models["llama3:8b"], models["qwen3.5:9b"]
    assert (llama["rating"], qwen["rating"]) == (None, None)
    assert llama["no_rating"] == qwen["no_rating"] == "no_anchor_path"
    assert (llama["rank"], qwen["rank"]) == (None, None)
    assert record(llama) == (10, 7, 0, 3, 0)
    assert record(qwen) == (10, 3, 0, 7, 0)


def test_anchor_matches_alone_give_a_rating_against_anchors_only(ranking):
    pooled = by_model(ranking(*MIXED))
    anchored = by_model(ranking(*MIXED, modes=["anchor_match"]))

    qwen = anchored["qwen3.5:9b"]
    assert record(qwen) == (10, 5, 0, 5, 0)
    assert qwen["rating"]["rated_games"] == 10 and pooled["qwen3.5:9b"]["rating"]["rated_games"] == 20
    assert qwen["rating"] != pooled["qwen3.5:9b"]["rating"]  # fitted from the subset, not filtered from the pool
    llama = anchored["llama3:8b"]
    assert (llama["rating"], llama["no_rating"], record(llama)) == (None, "no_reference_games", (0, 0, 0, 0, 0))


def test_play_llm_never_gives_a_rating_only_the_record_and_the_move_quality_estimate(ranking):
    analysed = (reference(game(HUMAN, LLAMA, "0-1"))[0], analysis({"black": [1400] * 10}))
    models = by_model(ranking(*MIXED, analysed, modes=["play_llm"]))

    llama = models["llama3:8b"]
    assert (llama["rating"], llama["no_rating"]) == (None, "play_llm_only")
    assert record(llama) == (5, 5, 0, 0, 0)
    assert llama["move_quality"]["games"] == 1
    assert models["qwen3.5:9b"]["no_rating"] == "no_reference_games"
    assert by_model(ranking(*MIXED, analysed, modes=["anchor_match"]))["llama3:8b"]["move_quality"] is None


def test_the_move_quality_estimate_pools_only_reference_games(ranking):
    analysed = analysis({"black": [1400] * 10})
    [llama] = ranking(
        (reference(game(HUMAN, LLAMA, "1-0"))[0], analysed),
        (game(HUMAN, LLAMA, "1-0"), analysed),  # 4 attempts a turn
    )

    assert llama["move_quality"]["games"] == 1


def test_two_modes_together(ranking):
    models = by_model(ranking(*MIXED, modes=["play_llm", "anchor_match"]))

    assert record(models["llama3:8b"]) == (4, 4, 0, 0, 0)
    assert models["qwen3.5:9b"]["rating"] is not None


def test_no_games_is_an_empty_ranking(ranking):
    assert ranking() == []


def test_an_unknown_mode_is_refused(tmp_path):
    client = TestClient(create_app(lambda settings, color: None, games_dir=tmp_path))

    assert client.get("/api/ranking", params={"mode": "simul"}).status_code == 422
