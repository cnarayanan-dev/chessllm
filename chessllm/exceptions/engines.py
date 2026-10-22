from chessllm.exceptions import ChessLlmError


class AnchorUnavailable(ChessLlmError):
    """The Anchor can't play: its engine isn't configured, isn't there, won't start or stopped answering."""

    code = "anchor_unavailable"


class StockfishUnavailable(ChessLlmError):
    """Stockfish can't be started: it isn't installed, or it won't run."""

    code = "stockfish_unavailable"


class Maia2Unavailable(ChessLlmError):
    """Maia-2 can't be started: uv is missing, or its environment or model can't be set up."""

    code = "maia2_unavailable"
