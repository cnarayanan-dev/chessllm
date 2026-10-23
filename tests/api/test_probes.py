"""Probes (CONTEXT.md, ADR 0010): the LLM of a past turn asked again about that turn's position, with any Prompt
template, outside the game. Each is judged as an attempt and appended to the game's probe log, never to its game log,
and a game's probes are listed again after a restart."""

import json
import random
import threading

import chess
from fastapi.testclient import TestClient

from tests.conftest import BlockingPlayer, Raw, ScriptedPlayer, play_llm, play_move

from chessllm.api.app import create_app
from chessllm.game.llm_turn.prompt import TurnPosition, fresh_prompt, side_template
from chessllm.game.session import GameSession
from chessllm.game.settings import Settings
from chessllm.game.sides import LlmSide, PromptTemplate
from chessllm.llm.models import LLM_MODELS
from chessllm.logs.game_log import GameLog

AFTER_E4 = chess.Board("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1")


def library(client) -> dict[str, dict]:
    """The library's templates by name."""
    return {entry["name"]: entry for entry in client.get("/api/prompt-templates").json()}


def template_of(entry: dict) -> PromptTemplate:
    return PromptTemplate(entry["id"], entry["name"], entry["system_prompt"], entry["turn_template"])


def probe(client, ply: int, color: str, template_id: str):
    return client.post("/api/games/current/probes", json={"ply": ply, "color": color, "prompt_template_id": template_id})


def two_moves_in(scripted, *replies: str | Raw, **llm):
    """Play LLM, the LLM Black, after 1. e4 e5 2. Nf3 Nc6; its later replies answer the probes."""
    client, player = scripted(["e5", "Nc6", *replies])
    assert client.post("/api/games", json=play_llm(**llm)).status_code == 200
    play_move(client, "e2e4")
    play_move(client, "g1f3")
    return client, player


def test_a_probe_sends_a_fresh_prompt_for_the_position_before_its_ply_built_from_the_given_template(scripted):
    client, player = two_moves_in(scripted, "d5")
    described = library(client)["Described"]

    response = probe(client, 2, "black", described["id"])

    assert response.status_code == 200, response.text
    expected = fresh_prompt(template_of(described), "black", TurnPosition(AFTER_E4, ["e4"]))
    assert player.prompts[-1] == expected
    assert expected[1].content.splitlines()[:3] == ["PGN: 1. e4", f"FEN: {AFTER_E4.fen()}", "Last move: e4"]
    assert response.json()["attempt"]["prompt"] == [
        {"role": message.role, "content": message.content} for message in expected
    ]
    assert len(player.prompts) == 3  # one call: the probe's


def test_a_probe_asks_with_the_sides_model_thinking_and_llm_constraints(scripted):
    client, player = scripted(["e5", "d5"], thinking=["e5 mirrors it.", "d5 strikes back."])
    client.post("/api/games", json=play_llm(model="qwen3.5:9b", thinking=True, llm_constraints="listed_enforced"))
    play_move(client, "e2e4")

    probed = probe(client, 2, "black", library(client)["Described listed"]["id"]).json()

    assert player.built_for[-1].black == LlmSide(model="qwen3.5:9b", thinking=True, llm_constraints="listed_enforced")
    assert sorted(player.allowed_moves[-1]) == sorted(AFTER_E4.san(move) for move in AFTER_E4.legal_moves)
    assert "\nLegal moves: " in player.prompts[-1][1].content
    assert probed["side"]["model"] == "qwen3.5:9b" and probed["side"]["llm_constraints"] == "listed_enforced"
    assert probed["attempt"]["thinking"] == "d5 strikes back."


def test_a_template_that_doesnt_fit_the_sides_llm_constraints_is_refused(scripted):
    client, player = two_moves_in(scripted)

    response = probe(client, 2, "black", library(client)["Default listed"]["id"])
    unknown = probe(client, 2, "black", "edited@00000000")

    assert (response.status_code, response.json()["code"]) == (400, "invalid_prompt_template")
    assert (unknown.status_code, unknown.json()["code"]) == (400, "unknown_prompt_template")
    assert unknown.json()["detail"] == "The Prompt library has no Prompt template edited@00000000 to probe with"
    assert len(player.prompts) == 2


def test_without_a_template_id_a_probe_asks_with_the_template_the_game_recorded_for_the_side(scripted, tmp_path):
    client, player = two_moves_in(scripted, "d5")
    state = client.get("/api/games/current").json()
    default = library(client)["Default"]
    [log] = (tmp_path / "games").glob("*.jsonl")
    played = json.loads(log.read_text(encoding="utf-8").splitlines()[0])["black"]["prompt_template"]

    response = client.post("/api/games/current/probes", json={"ply": 2, "color": "black"})

    assert state["prompt_template_ids"] == {"black": default["id"]} == {"black": played["id"]}
    assert response.status_code == 200, response.text
    assert response.json()["template"] == {"name": None} | played
    assert player.prompts[-1] == fresh_prompt(template_of(default), "black", TurnPosition(AFTER_E4, ["e4"]))


def test_a_probe_under_listed_shows_the_moves_in_an_order_of_the_positions_own(scripted):
    client, player = scripted(["e5", "d5", "d5"])
    client.post("/api/games", json=play_llm(llm_constraints="listed"))
    play_move(client, "e2e4")
    listed = library(client)["Default listed"]["id"]
    random.seed(7)
    before = random.getstate()

    probe(client, 2, "black", listed)
    probe(client, 2, "black", listed)

    assert random.getstate() == before  # the game's own random order of the Listed sides' lists is untouched
    assert player.prompts[-1][1].content == player.prompts[-2][1].content


def test_only_a_past_llm_turn_can_be_probed(scripted):
    client, _ = two_moves_in(scripted)
    default = library(client)["Default"]["id"]

    responses = [probe(client, 3, "white", default), probe(client, 6, "black", default), probe(client, 2, "white", default)]

    assert [(response.status_code, response.json()["code"]) for response in responses] == [(404, "no_llm_turn")] * 3


def test_a_probe_is_judged_like_an_attempt(scripted):
    client, _ = two_moves_in(scripted, "Qh4", "Nf6", "c5", "e7e5", Raw("I resign."))
    default = library(client)["Default"]["id"]

    probes = [probe(client, 2, "black", default).json()["attempt"] for _ in range(5)]

    judged = [(attempt["move"], attempt["san"], attempt["result"], attempt["notation_slip"]) for attempt in probes]
    assert judged == [
        ("Qh4", None, "illegal", False),
        ("Nf6", "Nf6", "legal", False),
        ("c5", "c5", "legal", False),
        ("e7e5", "e5", "legal", True),
        ("I resign.", None, "invalid", False),
    ]


def test_a_probe_that_gets_no_answer_says_why(scripted):
    client, _ = two_moves_in(scripted, TimeoutError("connection lost"))

    attempt = probe(client, 2, "black", library(client)["Default"]["id"]).json()["attempt"]

    assert (attempt["result"], attempt["raw_reply"]) == ("error", None)
    assert "did not reply" in attempt["error"]


def probe_log(tmp_path, game_id: str) -> list[dict]:
    path = tmp_path / "games" / "probes" / f"{game_id}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_each_probe_is_appended_to_the_probe_log_with_its_full_prompt_and_template_text(scripted, tmp_path):
    client, _ = two_moves_in(scripted, Raw(json.dumps({"reasoning": "Hit the knight.", "move": "Nf6"})))
    described = library(client)["Described"]
    state = client.get("/api/games/current").json()

    probed = probe(client, 2, "black", described["id"]).json()

    [logged] = probe_log(tmp_path, state["game_id"])
    assert logged["type"] == "probe"
    assert {key: logged[key] for key in ("game_id", "ply", "color", "fen", "pgn")} == {
        "game_id": state["game_id"], "ply": 2, "color": "black", "fen": AFTER_E4.fen(), "pgn": "1. e4",
    }
    assert logged["game_log"].endswith("_human_vs_llama3-8b.jsonl")
    assert logged["template"] == {key: described[key] for key in ("id", "name", "system_prompt", "turn_template")}
    assert logged["side"] == {
        "player": "llm", "model": "llama3:8b", "thinking": False, "llm_constraints": "free",
        "retry_feedback": "explained",
    }
    assert logged["sampling"] == {}
    attempt = logged["attempt"]
    assert attempt["prompt"] == probed["attempt"]["prompt"]
    assert (attempt["raw_reply"], attempt["reasoning"], attempt["result"]) == (
        '{"reasoning": "Hit the knight.", "move": "Nf6"}', "Hit the knight.", "legal",
    )
    assert attempt["latency_s"] == 0.0 and "probed_at" in logged
    assert {key: logged[key] for key in probed} == probed


def test_the_game_log_is_unchanged_byte_for_byte_by_any_number_of_probes(scripted, tmp_path):
    client, _ = two_moves_in(scripted, "d5", "Nf6", "Qh4")
    [log] = (tmp_path / "games").glob("*.jsonl")
    before = log.read_bytes()
    state = client.get("/api/games/current").json()

    for name in ("Default", "Described", "Default"):
        assert probe(client, 4 if name == "Described" else 2, "black", library(client)[name]["id"]).status_code == 200

    assert log.read_bytes() == before
    assert client.get("/api/games/current").json() == state
    assert [path.name for path in (tmp_path / "games").glob("*.jsonl")] == [log.name]


def test_a_probe_asked_while_an_llm_turn_runs_is_refused(tmp_path):
    player = BlockingPlayer(["e5", "Nc6"])
    client = TestClient(
        create_app(
            player.for_settings, games_dir=tmp_path / "games", sampling_file=tmp_path / "no-sampling.toml",
            prompt_library_dir=tmp_path / "prompt_library",
        )
    )
    client.post("/api/games")
    player.release.set()
    play_move(client, "e2e4")
    player.release.clear()
    player.asked.clear()
    client.post("/api/games/current/moves", json={"uci": "g1f3"})
    running = threading.Thread(target=lambda: client.post("/api/games/current/llm-turn"))
    running.start()
    assert player.asked.wait(timeout=5)

    response = probe(client, 2, "black", library(client)["Default"]["id"])
    player.release.set()
    running.join(timeout=5)

    assert (response.status_code, response.json()["code"]) == (409, "llm_turn_running")
    assert "LLM turn" in response.json()["detail"]
    assert len(player.prompts) == 2
    assert not (tmp_path / "games" / "probes").exists()


def test_an_llm_turn_asked_for_while_a_probe_runs_waits_for_it(tmp_path):
    player = BlockingPlayer(["e5", "d5", "Nc6"])
    client = TestClient(
        create_app(
            player.for_settings, games_dir=tmp_path / "games", sampling_file=tmp_path / "no-sampling.toml",
            prompt_library_dir=tmp_path / "prompt_library",
        )
    )
    client.post("/api/games")
    player.release.set()
    play_move(client, "e2e4")
    player.release.clear()
    player.asked.clear()
    client.post("/api/games/current/moves", json={"uci": "g1f3"})
    probes = []
    probing = threading.Thread(
        target=lambda: probes.append(probe(client, 2, "black", library(client)["Default"]["id"]))
    )
    probing.start()
    assert player.asked.wait(timeout=5)
    turns = []
    turn = threading.Thread(target=lambda: turns.append(client.post("/api/games/current/llm-turn")))
    turn.start()
    player.release.set()
    probing.join(timeout=5)
    turn.join(timeout=5)

    assert probes[0].json()["attempt"]["move"] == "d5"
    assert turns[0].status_code == 200 and turns[0].json()["pgn"] == "1. e4 e5 2. Nf3 Nc6"


def test_a_games_probes_are_listed_in_order_after_a_restart(scripted, tmp_path):
    client, _ = two_moves_in(scripted, "d5", "Nf6", "a6")
    game_id = client.get("/api/games/current").json()["game_id"]
    names = ["Default", "Described", "Default"]
    asked = [probe(client, ply, "black", library(client)[name]["id"]).json() for ply, name in zip([2, 4, 2], names)]

    restarted, _ = scripted([])
    listed = restarted.get(f"/api/games/{game_id}/probes")

    assert listed.status_code == 200
    assert listed.json() == asked
    assert [(entry["ply"], entry["template"]["name"], entry["attempt"]["move"]) for entry in listed.json()] == [
        (2, "Default", "d5"), (4, "Described", "Nf6"), (2, "Default", "a6"),
    ]


def test_a_game_without_probes_lists_none(scripted):
    client, _ = two_moves_in(scripted)
    game_id = client.get("/api/games/current").json()["game_id"]

    assert client.get(f"/api/games/{game_id}/probes").json() == []
    assert client.get("/api/games/not-a-game-id/probes").status_code == 422


def test_an_unreadable_line_of_a_probe_log_is_skipped(scripted, tmp_path):
    client, _ = two_moves_in(scripted, "d5")
    game_id = client.get("/api/games/current").json()["game_id"]
    asked = probe(client, 2, "black", library(client)["Default"]["id"]).json()
    with (tmp_path / "games" / "probes" / f"{game_id}.jsonl").open("a", encoding="utf-8") as file:
        file.write('{"type": "probe", "game_id": "')  # a write cut off

    assert client.get(f"/api/games/{game_id}/probes").json() == [asked]


def test_a_forfeited_turn_is_probed_in_the_position_it_forfeited_in(scripted):
    client, player = scripted(["Qh4", "Ke7", "Kd6", "e5"])
    client.post("/api/games", json=play_llm() | {"max_attempts": 3})
    play_move(client, "e2e4")  # three illegal moves: the LLM forfeits

    response = probe(client, 2, "black", library(client)["Default"]["id"])

    assert response.status_code == 200, response.text
    assert player.prompts[-1][1].content == f"PGN: 1. e4\nFEN: {AFTER_E4.fen()}"
    assert response.json()["attempt"]["result"] == "legal"


def test_a_side_keeping_a_conversation_is_probed_with_a_fresh_prompt(tmp_path):
    side = LlmSide(model="llama3:8b", turn_memory="chat_position")
    settings = Settings("llm_faceoff", side, side)
    settings.check(LLM_MODELS)
    white, black = ScriptedPlayer(["e4", "Nf3", "d4"]), ScriptedPlayer(["e5", "Nc6"])
    game = GameSession({"white": white, "black": black}, settings, GameLog(tmp_path, *settings.side_names()))
    for _ in range(4):
        game.play_llm_turn()

    probed = game.probe(3, "white", side_template(side))

    after_e4_e5 = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
    assert white.prompts[-1] == fresh_prompt(side_template(side), "white", TurnPosition(after_e4_e5, ["e4", "e5"]))
    assert [message.role for message in white.prompts[1]] == ["system", "user", "assistant", "user"]  # the game's turn
    assert probed.attempt.move == "d4"
