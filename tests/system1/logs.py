"""Hand-written game logs with System 1 sides, shaped as the runner writes them (tests/system1/test_runner.py): a
`system1_turn` for each of their turns, an `anchor_move` for each Anchor's, no `llm_attempt`."""

from dataclasses import dataclass
from typing import Any

import chess

PROMPT_TEMPLATE = {"id": "system1@6b0c92ff", "name": "System 1", "system_prompt": "Which move should $color play?",
                   "turn_template": "Moves so far: $moves\nFEN: $fen\n$description"}


@dataclass
class Turn:
    """A System 1 turn: the move played (None for a Forfeit) and the probability it gave each option in the order shown.
    No options is a turn that wasn't asked, as it had only one legal move (its move is then the only option)."""

    san: str | None
    options: dict[str, float | None] | None = None  # a Forfeit's options have no probabilities


def system1_side(model: str = "d3:2b", choice_temperature: float = 1.0, template: dict[str, Any] | None = None) -> dict:
    return {"player": "system1", "model": model, "base_url": "http://localhost:11434",
            "choice_temperature": choice_temperature, "prompt_template": template or PROMPT_TEMPLATE}


def anchor_side(skill: int = 1) -> dict:
    return {"player": "anchor", "engine": "dragon", "skill": skill}


def system1_game(white: dict, black: dict, plies: list[str | Turn], result: str | None = None, reason: str | None = None,
                 started: str = "2026-10-20T10:00:00+02:00", mode: str = "anchor_match") -> list[dict[str, Any]]:
    """The events of a game in which each ply is the SAN of an Anchor's move or a Turn of a System 1 side. Ends with
    game_end if there is a result. A System 1 side's stats are null, as the session leaves them."""
    events: list[dict[str, Any]] = [
        {"type": "game_start", "game_id": "s1", "log_version": 2, "mode": mode, "white": white, "black": black,
         "seed": 7, "sampling": "model_default", "max_retries": 3, "started_at": started}
    ]
    board = chess.Board()
    for ply, played in enumerate(plies, start=1):
        color = "white" if board.turn == chess.WHITE else "black"
        if isinstance(played, str):
            board.push_san(played)
            events.append({"type": "anchor_move", "color": color, "ply": ply, "move": played, "fen_after": board.fen(),
                           "time_s": 0.0})
            continue
        event: dict[str, Any] = {"type": "system1_turn", "color": color, "ply": ply, "asked": played.options is not None}
        if played.options is not None:
            event |= {"state": f"FEN: {board.fen()}", "question": f"Which move should {color.capitalize()} play?"}
        shown = played.options or {played.san: None}
        event["options"] = [{"san": san} | ({} if probability is None else {"probability": probability})
                            for san, probability in shown.items()]
        if played.san is None:
            event["error"] = "connection refused"
        else:
            move = board.push_san(played.san)
            event |= {"move": move.uci(), "san": played.san}
        events.append(event | {"time_s": 0.5})
    if result is not None:
        events.append({"type": "game_end", "result": result, "reason": reason, "plies": len(plies),
                       "stats": {"white": None, "black": None}, "time_used": {"white": 0.0, "black": 0.0}})
    return events
