"""The page rebuilds a conversation's whole Prompt from the records too (ADR 0009), in
frontend/src/components/turn/conversation.ts. Both rebuild it from the same fixture, scripted games' LLM turns and
every Prompt their LLMs were sent, so the two stay in step: here full_prompt and counterpart_prompt, there the page's
rebuilds.

The games, in each White keeping a conversation and Black playing fresh: in "trimmed" it is trimmed once at a turn's
start and once within a turn, after an illegal move. In "chaos", under Chaos rules, each side's chaos move has its
Legal counterpart asked. In "moves" White chats with moves under Retry feedback repeat, an illegal move left out of
its conversation. In "aside", under Chaos rules, White's counterpart is trimmed to the context on its own. After a change to what a game records, write the fixture
again:

    uv run python -m tests.game.test_conversation_fixture
"""

import json
import tempfile
from pathlib import Path
from typing import Any

from tests.fakes import FakeClock, ScriptedPlayer

from chessllm.core.types import Color
from chessllm.game.llm_turn.conversation import counterpart_prompt, full_prompt
from chessllm.game.records import LlmTurn
from chessllm.game.session import GameSession
from chessllm.game.settings import Settings
from chessllm.game.sides import LlmSide, PromptTemplate
from chessllm.llm.models import LLM_MODELS
from chessllm.llm.players import Message
from chessllm.logs.game_log import GameLog

FIXTURE = Path(__file__).parents[2] / "frontend" / "src" / "components" / "turn" / "conversation.fixture.json"
# Short, so the fixture reads at a glance; trimming follows the prompt tokens the scripted LLM reports.
TEMPLATE = PromptTemplate(id="chat@1", name=None, system_prompt="You play $color.", turn_template="$moves")
CHAT = LlmSide(model="llama3:8b", turn_memory="chat_position", prompt_template=TEMPLATE)
FRESH = LlmSide(prompt_template=TEMPLATE)
MOVES = LlmSide(
    model="llama3:8b",
    turn_memory="chat_moves",
    retry_feedback="repeat",
    prompt_template=PromptTemplate(
        id="moves@1", name=None, system_prompt="You play $color.", turn_template="$opponent_played"
    ),
)


def shape(messages: list[Message]) -> list[dict[str, str]]:
    return [{"role": message.role, "content": message.content} for message in messages]


def played(games_dir: Path, settings: Settings, players: dict[Color, ScriptedPlayer], plies: int) -> dict[str, Any]:
    """A game's LLM turns as the API gives them, every attempt's Prompt as the LLM received it, and every Legal
    counterpart's, each asked right after its chaos move's turn."""
    settings.check(LLM_MODELS)
    game = GameSession(dict(players), settings, GameLog(games_dir, *settings.side_names()), clock=FakeClock())
    for _ in range(plies):
        game.play_llm_turn()
    turns = game.state().llm_turns
    sent = {color: iter(player.prompts) for color, player in players.items()}
    prompts, counterparts = [], []
    for turn in turns:
        for number in range(1, len(turn.attempts) + 1):
            prompts.append({"ply": turn.ply, "attempt": number, "prompt": shape(next(sent[turn.color]))})
        if turn.legal_counterpart is not None:
            counterparts.append({"ply": turn.ply, "prompt": shape(next(sent[turn.color]))})
    return {
        "llm_turns": [turn.model_dump(mode="json", by_alias=True) for turn in turns],
        "prompts": prompts,
        "counterparts": counterparts,
    }


def scripted_games(games_dir: Path) -> dict[str, Any]:
    """The fixture: its four games."""
    trimmed = {
        "white": ScriptedPlayer(["f3", "g4", "h3", "Qxf7", "a3", "b3"]),
        "black": ScriptedPlayer(["e5", "d6", "c6", "a6"]),
    }
    trimmed["white"].usage = [{"prompt_tokens": tokens} for tokens in (50, 7680, 60, 7680, 70, 80)]
    # 1. Bd3 (chaos; its counterpart e4) Bc5 (chaos; its counterpart e5) 2. Nf3 Nf6
    chaos = {"white": ScriptedPlayer(["Bd3", "e4", "Nf3"]), "black": ScriptedPlayer(["Bc5", "e5", "Nf6"])}
    # 1. f3 e5 2. Qxf7?? (illegal, left out under repeat) g4 d6 3. h3, White chatting with moves.
    moves = {"white": ScriptedPlayer(["f3", "Qxf7", "g4", "h3"]), "black": ScriptedPlayer(["e5", "d6"])}
    # 1. f3 e5 2. Bd3 (chaos; its counterpart Nh3, asked in a conversation trimmed for it alone) d6 3. Nh3 c6
    aside = {"white": ScriptedPlayer(["f3", "Bd3", "Nh3", "Nh3"]), "black": ScriptedPlayer(["e5", "d6", "c6"])}
    aside["white"].usage = [{"prompt_tokens": tokens} for tokens in (50, 7680, 60, 70)]
    return {
        "trimmed": played(games_dir / "trimmed", Settings("llm_faceoff", CHAT, FRESH), trimmed, 9),
        "chaos": played(
            games_dir / "chaos", Settings("llm_faceoff", CHAT, FRESH, rules="chaos", legal_counterpart=True), chaos, 4
        ),
        "moves": played(games_dir / "moves", Settings("llm_faceoff", MOVES, FRESH), moves, 5),
        "aside": played(
            games_dir / "aside", Settings("llm_faceoff", CHAT, FRESH, rules="chaos", legal_counterpart=True), aside, 6
        ),
    }


def test_the_fixture_is_the_scripted_games_records_and_prompts(tmp_path):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert fixture == scripted_games(tmp_path), "write it again: uv run python -m tests.game.test_conversation_fixture"


def test_full_prompt_and_counterpart_prompt_rebuild_every_prompt_of_the_fixture():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    for game in fixture.values():
        turns = [LlmTurn.model_validate(turn) for turn in game["llm_turns"]]
        rebuilt = [shape_of(full_prompt(turns, sent["ply"], sent["attempt"])) for sent in game["prompts"]]
        assert rebuilt == [sent["prompt"] for sent in game["prompts"]]
        rebuilt = [shape_of(counterpart_prompt(turns, sent["ply"])) for sent in game["counterparts"]]
        assert rebuilt == [sent["prompt"] for sent in game["counterparts"]]
    white = [LlmTurn.model_validate(turn) for turn in fixture["trimmed"]["llm_turns"] if turn["color"] == "white"]
    # What the fixture covers: a turn that forgot earlier ones, an attempt that forgot more within its turn, and a
    # counterpart of each side, one asked in a conversation and one fresh.
    assert [turn.remembered for turn in white] == [0, 1, 1, 2, 2]
    assert [attempt.remembered for attempt in white[3].attempts] == [None, 1]
    assert [sent["ply"] for sent in fixture["chaos"]["counterparts"]] == [1, 2]
    moves = [LlmTurn.model_validate(turn) for turn in fixture["moves"]["llm_turns"]]
    assert [attempt.result for attempt in moves[2].attempts] == ["illegal", "legal"]
    assert moves[2].attempts[1].prompt == []  # under repeat the retry adds nothing
    aside = [LlmTurn.model_validate(turn) for turn in fixture["aside"]["llm_turns"]]
    counterpart = aside[2].legal_counterpart
    assert counterpart is not None and (aside[2].remembered, counterpart.attempt.remembered) == (1, 0)


def shape_of(prompt: list[Any]) -> list[dict[str, str]]:
    return [message.model_dump(mode="json") for message in prompt]


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as games_dir:
        FIXTURE.write_text(json.dumps(scripted_games(Path(games_dir)), indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {FIXTURE}")
