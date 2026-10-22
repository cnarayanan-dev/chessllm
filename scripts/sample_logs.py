"""Write the sample games (docs/samples/): four scripted games' logs and PGNs, and the API's responses while they
are played, so `git diff` shows what a refactor step changed in either. See docs/samples/README.md.

The LLMs and the Anchor are the scripted fakes of the tests (tests/fakes.py), so no Ollama or engine is needed. The
values that differ from run to run (game ids, timestamps, latencies, the repo's own path) are replaced with fixed ones,
so a file only changes when its content does.

Run: uv run python -m scripts.sample_logs
"""

import json
import random
import re
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from httpx2 import Response

from chessllm.game.runner import play_anchor_match
from chessllm.api.app import create_app
from chessllm.core.types import Color, Sampling
from chessllm.game.session import AnchorSide, BenchmarkLlmSide, LlmSide, Settings
from chessllm.logs.game_log import GameLog
from chessllm.llm.models import LLM_MODELS, load_sampling
from chessllm.llm.players import LlmPlayer
from chessllm.exceptions import LlmTimeout
from tests.fakes import Raw, ScriptedAnchor, ScriptedPlayer

ROOT = Path(__file__).parent.parent
SAMPLES_DIR = ROOT / "docs" / "samples"
# The sampling config every sample game is played at: an int and a float, as the log must keep each type (top_k 40,
# not 40.0).
SAMPLING_CONFIG = "temperature = 0.7\ntop_k = 40\n"


def reasoned(reasoning: str, move: str) -> Raw:
    """A reply with thinking off, as Ollama gives it: the Reasoning, then the move."""
    return Raw(json.dumps({"reasoning": reasoning, "move": move}))


def model_sampling(model: str) -> Sampling:
    """Stand-in for Ollama's `show`: each model's own sampling, or no answer for a model that isn't installed."""
    if model == "gemma4:26b":
        raise ConnectionError(f"model {model!r} not found")
    return {"temperature": 0.6, "top_k": 20, "top_p": 0.95}


class Samples:
    """The samples of one run, collected while the games are played and written once every game id is known."""

    def __init__(self, work_dir: Path) -> None:
        self.work_dir = work_dir
        self.sampling_file = work_dir / "sampling.toml"
        self.sampling_file.write_text(SAMPLING_CONFIG, encoding="utf-8")
        self.game_ids: list[str] = []  # in the order the games started, each to be replaced by its number
        self.games: list[str] = []  # each sample game's name, in the same order
        self.api: dict[str, Any] = {}  # each API sample's file name and its JSON
        self.errors: list[dict[str, Any]] = []  # each refused request with its status and response

    def games_dir(self, game: str) -> Path:
        return self.work_dir / game

    def client(self, game: str, players: dict[Color, ScriptedPlayer]) -> TestClient:
        """The app for one sample game, its LLM sides played by the given players."""

        def player_for(settings: Settings, color: Color) -> LlmPlayer:
            return players[color].for_settings(settings, color)

        app = create_app(
            player_for, games_dir=self.games_dir(game), sampling_defaults=model_sampling, sampling_file=self.sampling_file
        )
        return TestClient(app)

    def started(self, game: str, game_id: str) -> None:
        self.games.append(game)
        self.game_ids.append(game_id)

    def response(self, name: str, response: Response) -> Any:
        """Keep a response's JSON as the sample name.json, and return it."""
        assert response.status_code == 200, response.text
        self.api[name] = response.json()
        return self.api[name]

    def refused(self, client: TestClient, method: str, path: str, body: Any = None) -> None:
        """Send a request the API refuses, and keep it with its status and response for errors.json."""
        response = client.request(method, path, json=body)
        assert response.status_code != 200, response.text
        request = {"request": f"{method} {path}", "body": body}
        self.errors.append(request | {"status": response.status_code, "response": response.json()})

    def write(self, out: Path) -> None:
        for directory in (out / "game-logs", out / "api"):
            shutil.rmtree(directory, ignore_errors=True)
            directory.mkdir(parents=True)
        for number, game in enumerate(self.games, start=1):
            [log] = self.games_dir(game).glob("*.jsonl")
            for path in (log, log.with_suffix(".pgn")):
                text = self.fixed(path.read_text(encoding="utf-8"), number)
                (out / "game-logs" / f"{game}{path.suffix}").write_text(text, encoding="utf-8")
        for name, data in (self.api | {"errors": self.errors}).items():
            text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
            (out / "api" / f"{name}.json").write_text(self.fixed(text), encoding="utf-8")

    def fixed(self, text: str, number: int = 1) -> str:
        """The text with every run-dependent value fixed: each game id by its game's number, a log's times by those
        of its game's number (the games a minute apart), latencies by 0, and the repo's path left out of the prompt
        files' paths."""
        for game_number, game_id in enumerate(self.game_ids, start=1):
            text = text.replace(game_id, f"{game_number:032x}")
        text = text.replace(f"{ROOT}/", "")
        text = re.sub(r'"started_at": "[^"]*"', f'"started_at": "2026-01-01T10:{number:02}:00.000000+00:00"', text)
        text = re.sub(r'"ended_at": "[^"]*"', f'"ended_at": "2026-01-01T10:{number:02}:30+00:00"', text)
        text = re.sub(r'"latency_s": [0-9.e+-]+', '"latency_s": 0.0', text)
        return re.sub(r'\[Date "[^"]*"\]', '[Date "2026.01.01"]', text)


def play_llm_standard(samples: Samples) -> None:
    """Play LLM under Standard rules, the human as White: a human move, a notation slip, an illegal move then a
    Retry, and the LLM's checkmate (Fool's mate)."""
    game = "play-llm-standard"
    llm = ScriptedPlayer([
        reasoned("e7e5 takes the centre.", "e7e5"),  # a notation slip: UCI for e5
        reasoned("The queen takes on f2.", "Qxf2"),  # illegal: the queen can't reach f2
        reasoned("Qh4 is mate: g4 opened the diagonal.", "Qh4#"),
    ])
    client = samples.client(game, {"black": llm})
    new_game = {"mode": "play_llm", "white": {"player": "human"}, "black": {"player": "llm"}}
    state = samples.response(f"{game}-01-start", client.post("/api/games", json=new_game))
    samples.started(game, state["game_id"])
    samples.response(f"{game}-02-human-move", client.post("/api/games/current/moves", json={"uci": "f2f3"}))
    samples.response(f"{game}-03-llm-turn", client.post("/api/games/current/llm-turn"))
    samples.response(f"{game}-04-human-move", client.post("/api/games/current/moves", json={"uci": "g2g4"}))
    samples.response(f"{game}-05-llm-turn", client.post("/api/games/current/llm-turn"))
    samples.response(f"{game}-06-current", client.get("/api/games/current"))
    samples.refused(client, "POST", "/api/games/current/moves", {"uci": "e2e4"})  # the game is over
    samples.refused(client, "POST", "/api/games/current/llm-turn")


def llm_faceoff_chaos(samples: Samples) -> None:
    """An LLM faceoff under Chaos rules, White Listed with the position described: a chaos move, a Spawn, a Retry
    after badly formed notation (never a chaos move), and King capture."""
    game = "llm-faceoff-chaos"
    white = ScriptedPlayer(["e4", "Nf3", "Nxh4", "banana", "d3"])
    black = ScriptedPlayer([
        "Qh4",  # a chaos move: the queen goes through its own e7 pawn
        "a6",
        "Qd5",  # a Spawn: the queen was taken on h4
        "Qe1",  # King capture
    ])
    client = samples.client(game, {"white": white, "black": black})
    new_game = {
        "mode": "llm_faceoff",
        "white": {"player": "llm", "model": "gemma3:12b", "llm_constraints": "listed", "position": "described"},
        "black": {"player": "llm"},
        "rules": "chaos",
        "max_attempts": 3,
    }
    state = samples.response(f"{game}-01-start", client.post("/api/games", json=new_game))
    samples.started(game, state["game_id"])
    turn = 1
    while state["status"] == "playing":
        turn += 1
        state = samples.response(f"{game}-{turn:02}-llm-turn", client.post("/api/games/current/llm-turn"))


def anchor_match_standard(samples: Samples) -> None:
    """An Anchor match under Standard rules against a scripted Anchor, with three attempts per turn: Anchor moves,
    then an ambiguous, an illegal and a badly formed move, and the LLM's Forfeit."""
    game = "anchor-match-standard"
    llm = ScriptedPlayer(["e4", "Nc3", "Ne2", "Ke3", Raw("I resign.")])
    settings = Settings(
        "anchor_match",
        LlmSide(model="llama3:8b"),
        AnchorSide(engine="dragon", skill=1),
        sampling=load_sampling(samples.sampling_file),
        max_attempts=3,
    )
    play(samples, game, settings, {"white": llm}, {"black": ScriptedAnchor(["e5", "Nc6"])})


def llm_faceoff_thinking_budget(samples: Samples) -> None:
    """An LLM faceoff of two thinking sides with a Thinking budget each, as the benchmark plays them: a forced answer
    cut off at its token cap and its Retry, token counts, and a timeout, which forfeits at once."""
    game = "llm-faceoff-thinking-budget"
    white = ScriptedPlayer(
        [Raw(' {"mo'), "e4", "Nf3"], thinking=["e4 or d4, both", "e4 takes the centre.", "Nf3 develops."]
    )
    white.usage = [
        {"thinking_tokens": 1024, "answer_tokens": 64, "prompt_tokens": 412, "stop_reason": "length", "forced": True},
        {"thinking_tokens": 1024, "answer_tokens": 9, "prompt_tokens": 431, "stop_reason": "stop", "forced": True},
        {"thinking_tokens": 610, "answer_tokens": 8, "prompt_tokens": 420, "stop_reason": "stop",
         "token_split_estimated": True},
    ]
    black = ScriptedPlayer(["e5", LlmTimeout(316.0)], thinking=["e5 mirrors it."])
    black.usage = [{"thinking_tokens": 300, "answer_tokens": 8, "prompt_tokens": 415, "stop_reason": "stop"}]
    settings = Settings(
        "llm_faceoff",
        BenchmarkLlmSide(model="qwen3.8:latest", thinking=True, thinking_level="xhigh", thinking_budget=1024),
        BenchmarkLlmSide(model="qwen3.5:9b", thinking=True, thinking_budget=512),
        sampling=load_sampling(samples.sampling_file),
    )
    play(samples, game, settings, {"white": white, "black": black}, {})


def play(
    samples: Samples,
    game: str,
    settings: Settings,
    players: dict[Color, ScriptedPlayer],
    anchors: dict[Color, ScriptedAnchor],
) -> None:
    """Play an unattended game as the benchmark's commands do. No route serves its state, so only its log is kept."""
    settings.check(LLM_MODELS)
    log = GameLog(samples.games_dir(game), *settings.side_names())
    samples.started(game, log.game_id)
    llm_players: dict[Color, LlmPlayer] = {color: player for color, player in players.items()}
    play_anchor_match(settings, llm_players, dict(anchors), log)


def other_responses(samples: Samples) -> None:
    """The responses of the routes outside the sample games: the models, the new game's defaults, and requests the
    API refuses."""
    client = samples.client("other", {"black": ScriptedPlayer([])})
    samples.response("models", client.get("/api/models"))
    samples.response("games-defaults", client.get("/api/games/defaults"))
    samples.refused(client, "GET", "/api/games/current")  # no game started yet
    chaos_enforced = {"rules": "chaos", "black": {"player": "llm", "llm_constraints": "listed_enforced"}}
    samples.refused(client, "POST", "/api/games", chaos_enforced)
    samples.refused(client, "POST", "/api/games", {"max_attempts": 0})
    assert client.post("/api/games").status_code == 200  # a game with the defaults, to refuse moves in
    samples.refused(client, "POST", "/api/games/current/moves", {"uci": "e2e5"})
    samples.refused(client, "POST", "/api/games/current/moves", {"uci": "e2"})
    samples.refused(client, "POST", "/api/games/current/llm-turn")  # the human's turn


def leaderboard(game_logs: Path) -> dict[str, Any]:
    """The leaderboard of the sample games, read from their fixed logs."""
    app = create_app(lambda settings, color: ScriptedPlayer([]), games_dir=game_logs)
    response = TestClient(app).get("/api/leaderboard")
    assert response.status_code == 200, response.text
    data: dict[str, Any] = response.json()
    return data


def write_samples(out: Path = SAMPLES_DIR) -> None:
    """Play the sample games and write their logs, PGNs and API responses to out/game-logs and out/api, replacing
    those of an earlier run."""
    random.seed(84)  # Listed shows the legal moves in a random order
    games: list[Callable[[Samples], None]] = [
        play_llm_standard, llm_faceoff_chaos, anchor_match_standard, llm_faceoff_thinking_budget, other_responses,
    ]
    with tempfile.TemporaryDirectory() as work_dir:
        samples = Samples(Path(work_dir))
        for play_game in games:
            play_game(samples)
        samples.write(out)
    board = leaderboard(out / "game-logs")
    (out / "api" / "leaderboard.json").write_text(json.dumps(board, indent=2, ensure_ascii=False) + "\n", "utf-8")


def main() -> None:
    write_samples()
    print(f"Wrote the samples to {SAMPLES_DIR}")


if __name__ == "__main__":
    main()
