from chessllm.exceptions import ChessLlmError


class InvalidSamplingConfig(ChessLlmError):
    """The sampling config file is not valid TOML, sets an unknown option, or sets an option to something other than a number."""

    code = "config_error"
