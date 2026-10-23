"""The Ranking: one entry per model, from its games under the Reference configuration alone, ranked by the Rating
fitted from them (ADR 0011), with its Move-quality estimate and record. Narrowed to some Modes, every number comes from
those Modes' games alone."""

import json

import pytest
from fastapi.testclient import TestClient

from chessllm.analytics.leaderboard import PlayerConfiguration
from chessllm.analytics.ranking import is_reference, reference_configuration
from chessllm.api.app import create_app
from tests.analytics.test_leaderboard import HUMAN, LLAMA, QWEN, game, write_log
from tests.analytics.test_leaderboard_move_quality import analysis
from tests.analytics.test_leaderboard_rating import dragon, result_of

GEMMA = LLAMA | {"model": "gemma3:12b"}
QWEN_OFF = QWEN | {"thinking": False}  # qwen3.5:9b under the Reference configuration


def reference(events):
    """The game with 5 attempts per turn, as the Reference configuration plays: test_leaderboard's game() gives 4."""
    start, *rest = events
    return [start | {"max_retries": 4}, *rest]


def anchor_games(llm, skill, wins=0, draws=0, losses=0, forfeits=0, rules=None):
    """Anchor match games under the Reference configuration's attempts, colours alternating."""
    results = ["win"] * wins + ["draw"] * draws + ["loss"] * losses + ["forfeit"] * forfeits
    games = []
    for number, outcome in enumerate(results):
        llm_white = number % 2 == 0
        white, black = (llm, dragon(skill)) if llm_white else (dragon(skill), llm)
        reason = {"draw": "move_cap", "forfeit": "forfeit"}.get(outcome, "checkmate")
        result = result_of(outcome, llm_white)
        games.append(reference(game(white, black, result, reason, mode="anchor_match", rules=rules)))
    return games


def faceoff_games(first, second, wins=0, losses=0):
    results = ["win"] * wins + ["loss"] * losses
    return [
        reference(game(*((first, second) if n % 2 == 0 else (second, first)), result_of(outcome, n % 2 == 0)))
        for n, outcome in enumerate(results)
    ]


@pytest.fixture
def ranking(tmp_path):
    """Writes the given game logs, each alone or with its analysis file, into a fresh games directory and returns the
    Ranking's entries the API makes of them, narrowed to modes if given."""
    count = 0

    def make(*games, modes=None) -> list[dict]:
        nonlocal count
        count += 1
        games_dir = tmp_path / f"games-{count}"
        games_dir.mkdir()
        for number, item in enumerate(games):
            events, analysed = item if isinstance(item, tuple) else (item, None)
            name = f"2026-10-19T10-00-{number:02d}_game"
            write_log(games_dir, name, events)
            if analysed is not None:
                (games_dir / f"{name}.analysis.json").write_text(json.dumps(analysed), encoding="utf-8")
        app = create_app(
            lambda settings, color: None, games_dir=games_dir, move_quality_validation=tmp_path / "none.json"
        )
        response = TestClient(app).get("/api/ranking", params={"modes": modes} if modes else None)
        assert response.status_code == 200, response.text
        return response.json()["models"]

    return make


def with_start(games, **fields):
    """The games with fields changed in their game_start."""
    return [[start | fields, *rest] for start, *rest in games]


def by_model(entries):
    return {entry["model"]: entry for entry in entries}


def record(entry):
    return entry["games"], entry["wins"], entry["draws"], entry["losses"], entry["forfeits"]


REFERENCE = PlayerConfiguration(
    model="llama3:8b",
    thinking=False,
    llm_constraints="free",
    rules="standard",
    retry_feedback="explained",
    max_retries=4,
    sampling={},
    prompt="system.txt",
)


def test_the_reference_configuration_is_thinking_off_free_standard_rules_5_attempts_explained_fresh_no_tools():
    assert reference_configuration("llama3:8b") == REFERENCE
    assert reference_configuration("gemma3:12b") == REFERENCE.model_copy(update={"model": "gemma3:12b"})
    assert is_reference(REFERENCE)


@pytest.mark.parametrize(
    "change",
    [
        {"thinking": True},
        {"thinking": True, "thinking_level": "low"},
        {"thinking_budget": 400},
        {"llm_constraints": "listed"},
        {"llm_constraints": "listed_enforced"},
        {"rules": "chaos"},
        {"retry_feedback": "hinted"},
        {"max_retries": 0},
        {"sampling": {"temperature": 0.7}},
        {"prompt": "my-template@1"},
        {"position": "described"},
        {"turn_memory": "chat_position"},
        {"tools": ("board",), "tool_call_cap": 10},
    ],
    ids=lambda change: "+".join(change),
)
def test_a_configuration_differing_in_any_setting_but_the_model_is_not_the_reference(change):
    assert not is_reference(REFERENCE.model_copy(update=change))


def test_a_default_anchor_match_plays_under_the_reference_configuration(tmp_path):
    from chessllm.analytics.leaderboard import settings_configuration
    from chessllm.cli.anchor_match import parser
    from chessllm.cli.common import anchor_match_settings
    from chessllm.game.sides import AnchorSide

    args = parser().parse_args(["--model", "gemma3:12b"])
    settings = anchor_match_settings(args, "white", AnchorSide(skill=1), tmp_path / "no-sampling.toml")

    assert settings_configuration(settings, "white") == reference_configuration("gemma3:12b")


def test_an_anchor_match_with_tools_plays_their_prompt_and_is_not_the_reference(tmp_path):
    from chessllm.analytics.leaderboard import settings_configuration
    from chessllm.cli.anchor_match import parser
    from chessllm.cli.common import anchor_match_settings
    from chessllm.game.sides import AnchorSide

    args = parser().parse_args(["--model", "qwen3.5:9b", "--thinking", "--tools"])
    settings = anchor_match_settings(args, "white", AnchorSide(skill=1), tmp_path / "no-sampling.toml")
    configuration = settings_configuration(settings, "white")
    without_thinking = configuration.model_copy(update={"thinking": False})

    assert (configuration.prompt, len(configuration.tools)) == ("system_tools.txt", 4)
    assert not is_reference(without_thinking)
    assert not is_reference(without_thinking.model_copy(update={"tools": (), "tool_call_cap": None}))


def test_one_entry_per_model_ranked_by_its_rating_with_its_record(ranking):
    entries = ranking(
        *anchor_games(QWEN_OFF, 3, wins=5, draws=1, losses=4),  # about 500
        *anchor_games(LLAMA, 1, wins=3, losses=5, forfeits=2),  # below Skill 1 (250)
        *anchor_games(GEMMA, 1, losses=4, forfeits=2),  # lost every game: "< X"
    )

    assert [(entry["rank"], entry["model"]) for entry in entries] == [
        (1, "qwen3.5:9b"),
        (2, "llama3:8b"),
        (3, "gemma3:12b"),
    ]
    qwen, llama, gemma = entries
    assert record(qwen) == (10, 5, 1, 4, 0)
    assert record(llama) == (10, 3, 0, 7, 2)
    assert record(gemma) == (6, 0, 0, 6, 2)
    assert qwen["rating"]["low"] < 500 < qwen["rating"]["high"]
    assert llama["rating"]["estimate"] < 250
    assert (gemma["rating"]["estimate"], gemma["rating"]["low"]) == (None, None) and gemma["rating"]["high"] < 250
    assert [entry["no_rating"] for entry in entries] == [None, None, None]


def test_games_under_any_other_settings_are_left_out_of_the_ranking_entirely(ranking):
    games = [*anchor_games(LLAMA, 1, wins=4, losses=6), *faceoff_games(LLAMA, QWEN_OFF, wins=2, losses=2)]
    others = [
        *anchor_games(LLAMA, 7, wins=6, rules="chaos"),
        *anchor_games(LLAMA | {"llm_constraints": "listed"}, 7, wins=6),
        *anchor_games(LLAMA | {"thinking": True}, 7, wins=6),
        *with_start(anchor_games(LLAMA, 7, wins=6), max_retries=3),  # 4 attempts a turn
        *with_start(anchor_games(LLAMA, 7, wins=6), sampling={"temperature": 0.2}),
        *with_start(anchor_games(LLAMA, 7, wins=6), prompt_files={"white": "/x/my-prompt.txt"}),
        reference(game(HUMAN, LLAMA | {"thinking": True}, "0-1")),
        *faceoff_games(QWEN_OFF, LLAMA | {"llm_constraints": "listed"}, wins=6),  # one side not the reference
        *anchor_games(GEMMA | {"thinking": True}, 1, wins=6),  # gemma played only under other settings
    ]

    alone = ranking(*games)
    entries = ranking(*games, *others)

    assert entries[:2] == alone
    [gemma] = entries[2:]
    assert gemma["model"] == "gemma3:12b"
    assert (gemma["rank"], gemma["rating"], gemma["move_quality"], record(gemma)) == (None, None, None, (0,) * 5)
    assert gemma["no_rating"] == "no_reference_games"


def test_models_without_a_rating_are_listed_after_the_ranked_ones_unranked_with_the_reason(ranking):
    entries = ranking(
        *faceoff_games(GEMMA, QWEN_OFF, wins=3, losses=1),  # no path to an Anchor
        *anchor_games(LLAMA, 1, wins=4, losses=6),
        reference(game(HUMAN, LLAMA | {"model": "mistral:7b"}, "0-1")),  # Play LLM only
        game(HUMAN, LLAMA | {"model": "phi4:14b"}, "0-1"),  # not under the Reference configuration
    )

    assert [(entry["rank"], entry["model"], entry["no_rating"]) for entry in entries] == [
        (1, "llama3:8b", None),
        (None, "gemma3:12b", "no_path_to_anchor"),
        (None, "mistral:7b", "no_rated_games"),
        (None, "qwen3.5:9b", "no_path_to_anchor"),
        (None, "phi4:14b", "no_reference_games"),
    ]


def test_anchor_matches_alone_give_a_rating_refitted_from_them_alone(ranking):
    anchored = anchor_games(LLAMA, 3, wins=5, losses=5)
    # Faceoffs that drag llama down in the whole pool: it lost all of them to a model that lost to Skill 1.
    faceoffs = [*faceoff_games(LLAMA, QWEN_OFF, losses=8), *anchor_games(QWEN_OFF, 1, wins=1, losses=9)]

    pooled = by_model(ranking(*anchored, *faceoffs))["llama3:8b"]
    narrowed = by_model(ranking(*anchored, *faceoffs, modes=["anchor_match"]))
    alone = by_model(ranking(*anchored))["llama3:8b"]

    assert narrowed["llama3:8b"]["rating"] == alone["rating"]
    assert pooled["rating"]["estimate"] < alone["rating"]["estimate"]
    assert record(narrowed["llama3:8b"]) == (10, 5, 0, 5, 0)
    assert record(narrowed["qwen3.5:9b"]) == (10, 1, 0, 9, 0)


def test_llm_faceoffs_alone_give_no_ratings(ranking):
    games = [*anchor_games(LLAMA, 3, wins=5, losses=5), *faceoff_games(LLAMA, QWEN_OFF, wins=3, losses=1)]

    entries = ranking(*games, modes=["llm_faceoff"])

    assert [(entry["model"], entry["rank"], entry["rating"], entry["no_rating"]) for entry in entries] == [
        ("llama3:8b", None, None, "no_path_to_anchor"),
        ("qwen3.5:9b", None, None, "no_path_to_anchor"),
    ]
    assert [record(entry) for entry in entries] == [(4, 3, 0, 1, 0), (4, 1, 0, 3, 0)]


def test_play_llm_games_never_give_a_rating_only_the_record_and_the_move_quality_estimate(ranking):
    games = [
        *anchor_games(LLAMA, 3, wins=5, losses=5),
        (reference(game(HUMAN, LLAMA, "0-1")), analysis({"black": [1400] * 10})),
        (reference(game(LLAMA, HUMAN, "0-1", "forfeit")), analysis({"white": [1400] * 10})),
    ]

    [llama] = ranking(*games, modes=["play_llm"])

    assert (llama["rank"], llama["rating"], llama["no_rating"]) == (None, None, "no_rated_games")
    assert record(llama) == (2, 1, 0, 1, 1)
    assert (llama["move_quality"]["estimate"], llama["move_quality"]["games"]) == (964, 2)
    assert llama["move_quality"]["validated"] is False


def test_the_move_quality_estimate_pools_only_the_reference_games_in_the_chosen_modes(ranking):
    games = [
        (anchor_games(LLAMA, 3, wins=1)[0], analysis({"white": [1800] * 10})),
        (reference(game(HUMAN, LLAMA, "0-1")), analysis({"black": [1400] * 10})),
        (game(HUMAN, LLAMA, "0-1"), analysis({"black": [1000] * 30})),  # 4 attempts a turn
    ]

    [everything] = ranking(*games)
    [anchored] = ranking(*games, modes=["anchor_match"])

    assert everything["move_quality"]["games"] == 2
    assert (anchored["move_quality"]["games"], anchored["move_quality"]["lichess_rapid"]["estimate"]) == (1, 1800)


def test_the_ranking_names_the_modes_it_comes_from_all_by_default(tmp_path):
    client = TestClient(create_app(lambda settings, color: None, games_dir=tmp_path / "no-games-yet"))

    assert client.get("/api/ranking").json() == {"modes": ["play_llm", "llm_faceoff", "anchor_match"], "models": []}
    narrowed = client.get("/api/ranking", params={"modes": ["anchor_match", "play_llm"]}).json()
    assert narrowed["modes"] == ["play_llm", "anchor_match"]
    assert client.get("/api/ranking", params={"modes": ["chess960"]}).status_code == 422
