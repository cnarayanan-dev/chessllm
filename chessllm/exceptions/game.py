from chessllm.exceptions import ChessLlmError


class InvalidSettings(ChessLlmError):
    """A game can't be played with these settings; the message says why."""

    code = "invalid_settings"


class NoGameStarted(ChessLlmError):
    """There is no current game to show or play in: none has been started since the server started."""

    code = "no_current_game"

    def __init__(self) -> None:
        super().__init__("no game started")


class RejectedHumanMove(ChessLlmError):
    """A human's move can't be played: it is illegal (illegal_move) or not UCI (invalid_move), no human plays in
    the game (not_human_turn), or the game is over (game_over)."""

    code = "illegal_move"


class RefusedLlmTurn(ChessLlmError):
    """An LLM turn can't start: it isn't an LLM's turn (not_llm_turn), the game is over (game_over), or a turn is
    already running (llm_turn_running)."""

    code = "not_llm_turn"


class RefusedAnchorTurn(ChessLlmError):
    """An Anchor turn can't start: it isn't an Anchor's turn (not_anchor_turn), or the game is over (game_over)."""

    code = "not_anchor_turn"
