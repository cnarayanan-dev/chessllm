"""Probes (CONTEXT.md, ADR 0010): the LLM asked again about a past turn's position with any Prompt template, outside
the game, each recorded in the probe log next to the game's log, which no probe ever touches."""

from tests.conftest import BlockingPlayer, FakeClock, Raw, ScriptedPlayer, play_llm, play_move

import json
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chessllm.api.app import create_app
from chessllm.exceptions import InvalidSettings
from chessllm.game.llm_turn.prompt import default_template
from chessllm.game.session import GameSession
from chessllm.game.settings import Settings
from chessllm.game.sides import HumanSide, LlmSide
from chessllm.logs.game_log import GameLog

AFTER_NF3 = "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2"


def template_id(client, name: str) -> str:
    return next(entry["id"] for entry in client.get("/api/prompt-templates").json() if entry["name"] == name)


def two_moves_in(client, **llm) -> None:
    """1. e4 e5 2. Nf3 Nc6, the LLM playing Black with the given settings."""
    client.post("/api/games", json=play_llm(**llm))
    for uci in ["e2e4", "g1f3"]:
        assert play_move(client, uci).status_code == 200


def probe(client, ply: int, color: str, prompt_template_id: str):
    return client.post(
        "/api/games/current/probes", json={"ply": ply, "color": color, "prompt_template_id": prompt_template_id}
    )


def reasoned(reasoning: str, move: str) -> Raw:
    """A reply with thinking off: the Reasoning, then the move."""
    return Raw(json.dumps({"reasoning": reasoning, "move": move}))


def game_log(games_dir: Path) -> Path:
    [log] = games_dir.glob("*.jsonl")
    return log


def probe_log(games_dir: Path) -> list[dict]:
    [log] = games_dir.glob("*.probes.ndjson")
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def test_a_probe_sends_a_fresh_prompt_for_the_position_before_the_turn_built_from_the_template(scripted):
    client, player = scripted(["e5", "Nc6", "Nf6"])
    two_moves_in(client)

    response = probe(client, 4, "black", template_id(client, "Described"))

    assert response.status_code == 200, response.text
    [system, message] = player.prompts[-1]
    assert (system.role, system.content) == ("system", player.prompts[0][0].content)
    assert (message.role, message.content.splitlines()) == ("user", [
        "PGN: 1. e4 e5 2. Nf3",
        f"FEN: {AFTER_NF3}",
        "Last move: Nf3",
        "Your pieces (Black): King e8; Queen d8; Rooks a8, h8; Bishops c8, f8; Knights b8, g8; "
        "Pawns a7, b7, c7, d7, e5, f7, g7, h7",
        "Opponent's pieces (White): King e1; Queen d1; Rooks a1, h1; Bishops c1, f1; Knights b1, f3; "
        "Pawns a2, b2, c2, d2, e4, f2, g2, h2",
    ])


def test_a_probe_is_asked_with_the_sides_settings(scripted):
    client, player = scripted(["e5", "Nc6", "Nf6"])
    two_moves_in(client, model="qwen3.5:9b", llm_constraints="listed_enforced")

    response = probe(client, 4, "black", template_id(client, "Described listed"))

    assert response.status_code == 200, response.text
    assert len(player.built_for) == 1  # the game's own player: the same model, thinking and sampling
    listed = player.prompts[-1][1].content.splitlines()[-1]
    assert sorted(listed.removeprefix("Legal moves: ").split()) == sorted(player.allowed_moves[-1])
    assert "Nc6" in player.allowed_moves[-1] and len(player.allowed_moves[-1]) == 29
    assert response.json() | {"attempt": None, "prompt_template": None, "asked_at": None} == {
        "game_id": client.get("/api/games/current").json()["game_id"],
        "ply": 4,
        "color": "black",
        "model": "qwen3.5:9b",
        "thinking": False,
        "llm_constraints": "listed_enforced",
        "sampling": {},
        "prompt_template": None,
        "attempt": None,
        "asked_at": None,
    }


def test_a_probe_is_judged_like_an_attempt_and_kept_in_the_probe_log_with_its_prompt_and_template(scripted, tmp_path):
    slip, illegal = reasoned("Develop the knight.", "b8c6"), reasoned("Take on f2.", "Qxf2")
    client, player = scripted(["e5", "Nc6", slip, illegal])
    two_moves_in(client)
    described = next(entry for entry in client.get("/api/prompt-templates").json() if entry["name"] == "Described")

    first = probe(client, 4, "black", described["id"]).json()
    second = probe(client, 4, "black", described["id"]).json()

    judged = [(probe["attempt"]["move"], probe["attempt"]["san"], probe["attempt"]["notation_slip"],
               probe["attempt"]["result"], probe["attempt"]["reasoning"]) for probe in (first, second)]
    assert judged == [
        ("b8c6", "Nc6", True, "legal", "Develop the knight."),
        ("Qxf2", None, False, "illegal", "Take on f2."),
    ]
    logged = probe_log(tmp_path / "games")
    assert logged == [{"type": "probe", **first}, {"type": "probe", **second}]
    assert logged[1]["attempt"]["raw_reply"] == illegal
    assert logged[1]["attempt"]["prompt"] == [
        {"role": message.role, "content": message.content} for message in player.prompts[-1]
    ]
    assert logged[1]["prompt_template"] == {
        key: described[key] for key in ("id", "name", "system_prompt", "turn_template")
    }


def test_no_number_of_probes_changes_the_game_or_its_log(scripted, tmp_path):
    client, _ = scripted(["e5", "Nc6", "Nf6", Raw("no move"), RuntimeError("Ollama is down")])
    two_moves_in(client)
    log = game_log(tmp_path / "games")
    logged, state = log.read_bytes(), client.get("/api/games/current").json()

    for name in ["Default", "Described", "Default"]:
        assert probe(client, 4, "black", template_id(client, name)).status_code == 200

    assert log.read_bytes() == logged
    assert client.get("/api/games/current").json() == state
    assert [probe["attempt"]["result"] for probe in probe_log(tmp_path / "games")] == ["legal", "invalid", "error"]


def test_a_probe_asked_while_an_llm_turn_runs_is_refused(tmp_path):
    player = BlockingPlayer(["e5", "Nc6"])
    app = create_app(
        player.for_settings, games_dir=tmp_path / "games", sampling_file=tmp_path / "none.toml",
        prompt_library_dir=tmp_path / "library", clock=FakeClock(),
    )
    client = TestClient(app)
    client.post("/api/games", json=play_llm())
    client.post("/api/games/current/moves", json={"uci": "e2e4"})
    player.release.set()
    client.post("/api/games/current/llm-turn")
    client.post("/api/games/current/moves", json={"uci": "g1f3"})
    player.release.clear()
    player.asked.clear()
    turn = threading.Thread(target=client.post, args=["/api/games/current/llm-turn"])
    turn.start()
    assert player.asked.wait(timeout=5)

    response = probe(client, 2, "black", template_id(client, "Default"))
    player.release.set()
    turn.join()

    assert (response.status_code, response.json()["code"]) == (409, "llm_turn_running")
    assert len(player.prompts) == 2  # the two turns only
    assert not list((tmp_path / "games").glob("*.probes.ndjson"))


def test_an_llm_turn_asked_for_while_a_probe_runs_waits_for_it_rather_than_being_refused(tmp_path):
    """The page takes a refused LLM turn for one already running, and would wait for a turn that never lands."""
    player = BlockingPlayer(["e5", "d6", "Nc6"])
    app = create_app(
        player.for_settings, games_dir=tmp_path / "games", sampling_file=tmp_path / "none.toml",
        prompt_library_dir=tmp_path / "library", clock=FakeClock(),
    )
    client = TestClient(app)
    client.post("/api/games", json=play_llm())
    player.release.set()
    play_move(client, "e2e4")
    client.post("/api/games/current/moves", json={"uci": "g1f3"})
    player.release.clear()
    player.asked.clear()
    probed: list = []
    asking = threading.Thread(target=lambda: probed.append(probe(client, 2, "black", template_id(client, "Default"))))
    asking.start()
    assert player.asked.wait(timeout=5)

    turn: list = []
    playing = threading.Thread(target=lambda: turn.append(client.post("/api/games/current/llm-turn")))
    playing.start()
    playing.join(timeout=0.2)  # time for the turn's request to reach the game while the probe runs
    player.release.set()
    asking.join()
    playing.join()

    assert probed[0].status_code == 200 and probed[0].json()["attempt"]["move"] == "d6"
    assert turn[0].status_code == 200 and turn[0].json()["pgn"] == "1. e4 e5 2. Nf3 Nc6"


def test_a_games_probes_are_listed_in_order_after_a_restart(scripted, tmp_path):
    client, player = scripted(["e5", "Nc6", "Nf6", "d6", "a6"])
    two_moves_in(client)
    game_id = client.get("/api/games/current").json()["game_id"]
    asked = [probe(client, ply, "black", template_id(client, "Default")).json() for ply in (4, 2, 4)]

    restarted = TestClient(create_app(player.for_settings, games_dir=tmp_path / "games"))
    listed = restarted.get(f"/api/games/{game_id}/probes")

    assert listed.status_code == 200
    assert listed.json() == asked
    assert [(probe["ply"], probe["attempt"]["move"]) for probe in listed.json()] == [(4, "Nf6"), (2, "d6"), (4, "a6")]
    assert restarted.get("/api/games/another-game/probes").json() == []


def test_the_state_names_the_prompt_template_each_llm_side_plays_so_the_page_can_tell_it_apart(scripted, tmp_path):
    client, _ = scripted([])
    default, described = template_id(client, "Default"), template_id(client, "Described")

    on_default = client.post("/api/games", json=play_llm()).json()
    on_described = client.post("/api/games", json=play_llm(prompt_template_id=described)).json()
    settings = Settings("play_llm", HumanSide(), LlmSide(turn_memory="chat_moves"))
    on_moves = GameSession({"black": ScriptedPlayer([])}, settings, GameLog(tmp_path, "human", "llama3-8b")).state()

    assert on_default["prompt_templates"] == {"black": {"id": default, "name": "Default"}}
    assert on_described["prompt_templates"] == {"black": {"id": described, "name": "Described"}}
    assert on_moves.model_dump()["prompt_templates"] == {"black": {"id": default_template("free", "moves").id, "name": "Moves"}}


def test_a_probe_is_refused_for_a_turn_the_game_has_not_played_or_a_template_that_does_not_fit(scripted):
    client, player = scripted(["e5", "Nc6"])
    two_moves_in(client)

    refusals = [
        probe(client, 3, "white", template_id(client, "Default")),  # the human's move
        probe(client, 6, "black", template_id(client, "Default")),  # not played yet
        probe(client, 4, "black", template_id(client, "Default listed")),  # places the Legal-move list under Free
        probe(client, 4, "black", "edited@00000000"),
    ]

    assert [(response.status_code, response.json()["code"]) for response in refusals] == [
        (409, "no_llm_turn"),
        (409, "no_llm_turn"),
        (400, "invalid_prompt_template"),
        (400, "unknown_prompt_template"),
    ]
    assert len(player.prompts) == 2


def test_a_side_keeping_a_conversation_is_probed_with_a_fresh_prompt(tmp_path):
    player = ScriptedPlayer(["e5", "Nc6", "Nf6"])
    settings = Settings("play_llm", HumanSide(), LlmSide(turn_memory="chat_position"))
    session = GameSession({"black": player}, settings, GameLog(tmp_path, "human", "llama3-8b"))
    for uci in ["e2e4", "g1f3"]:
        session.play_human_move(uci)
        session.play_llm_turn()

    session.probe(4, "black", default_template("free"))

    assert len(player.prompts[1]) == 4  # the game's second turn holds the first
    assert [message.role for message in player.prompts[-1]] == ["system", "user"]
    assert player.prompts[-1][1].content == f"PGN: 1. e4 e5 2. Nf3\nFEN: {AFTER_NF3}"


def test_a_side_on_the_moves_template_is_probed_with_one_that_shows_the_position(tmp_path):
    """A fresh Prompt from the Moves template would show the LLM only the opponent's last move."""
    player = ScriptedPlayer(["e5", "Nc6", "Nf6"])
    settings = Settings("play_llm", HumanSide(), LlmSide(turn_memory="chat_moves"))
    session = GameSession({"black": player}, settings, GameLog(tmp_path, "human", "llama3-8b"))
    for uci in ["e2e4", "g1f3"]:
        session.play_human_move(uci)
        session.play_llm_turn()

    with pytest.raises(InvalidSettings, match="only the opponent's last move") as refused:
        session.probe(4, "black", default_template("free", "moves"))
    session.probe(4, "black", default_template("free"))

    assert refused.value.code == "invalid_prompt_template"
    assert len(player.prompts) == 3
    assert [message.role for message in player.prompts[-1]] == ["system", "user"]
    assert player.prompts[-1][1].content == f"PGN: 1. e4 e5 2. Nf3\nFEN: {AFTER_NF3}"
