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


class RefusedProbe(ChessLlmError):
    """A Probe can't be asked now: an LLM turn of the game is running (llm_turn_running), and a probe never runs
    alongside a real turn."""

    code = "llm_turn_running"


class NoLlmTurn(ChessLlmError):
    """The game has no LLM turn of that ply and colour to probe (no_llm_turn): it was a human's or an Anchor's ply,
    or isn't played yet."""

    code = "no_llm_turn"
