from chessllm.exceptions import ChessLlmError


class DecisionModelFailed(ChessLlmError):
    """A System 1 model's call failed: the server didn't answer in time, refused, answered with an error or with
    probabilities that don't match the options. The turn it came in is a Forfeit."""

    code = "decision_model_failed"


class System1Unavailable(ChessLlmError):
    """A System 1 model's server can't be asked which models it has: it isn't running, didn't answer in time, or
    failed."""

    code = "system1_unavailable"


class RefusedSystem1Turn(ChessLlmError):
    """A System 1 turn can't start: it isn't a System 1 model's turn (not_system1_turn), the game is over (game_over)
    or a turn is already running (system1_turn_running)."""

    code = "not_system1_turn"
