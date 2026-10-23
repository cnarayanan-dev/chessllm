"""Reading a game log's LLM turns back into the game's records (ADR 0008), so that what is rebuilt from the records,
such as a conversation's whole Prompt (game.llm_turn.conversation.full_prompt, ADR 0009), is rebuilt from a log the
same way."""

from collections.abc import Iterable
from typing import Any

from chessllm.core.types import COLORS
from chessllm.game.records import Attempt, LlmTurn


def logged_llm_turns(events: Iterable[dict[str, Any]]) -> list[LlmTurn]:
    """The LLM turns of a version 2 game log, in the order played, from its llm_attempt events: each attempt as its
    record has it, the log's thinking being the Reasoning when the side's thinking is off (Attempt.log_shape), and
    each turn's Time used and remembered as its attempts log them, the turn's being its first attempt's. Legal
    counterparts are left out."""
    thinks: dict[str, bool] = {}
    turns: dict[int, LlmTurn] = {}
    for event in events:
        if event["type"] == "game_start":
            thinks = {color: bool(event[color]["thinking"]) for color in COLORS if event[color]["player"] == "llm"}
        if event["type"] != "llm_attempt":
            continue
        thinking, reasoning = (event["thinking"], None) if thinks[event["color"]] else (None, event["thinking"])
        turn = turns.setdefault(
            event["ply"],
            LlmTurn(
                ply=event["ply"], color=event["color"], attempts=[], time_s=0.0, thinking=None, reasoning=None,
                remembered=event.get("remembered"),
            ),
        )
        # An attempt logs what it remembered; its record has it only when trimming within the turn made it differ.
        trimmed = event.get("remembered") if event.get("remembered") != turn.remembered else None
        attempt = Attempt.model_validate(event | {"thinking": thinking, "reasoning": reasoning, "remembered": trimmed})
        turn.attempts.append(attempt)
        turn.reasoning = reasoning  # the last attempt's: none without an answer
        if attempt.raw_reply is not None:
            turn.thinking = thinking  # the last that answered
        if "turn_time_s" in event:
            turn.time_s = event["turn_time_s"]
    return [turns[ply] for ply in sorted(turns)]
