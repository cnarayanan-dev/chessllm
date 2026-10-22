"""The Rules of a game, Standard or Chaos, looked up by the key the API and the game log give them."""

from chessllm.core.types import RulesKey
from chessllm.game.rules.base import Rules
from chessllm.game.rules.chaos import CHAOS
from chessllm.game.rules.standard import STANDARD

RULES: dict[RulesKey, Rules] = {"standard": STANDARD, "chaos": CHAOS}


def rules_named(key: object) -> Rules | None:
    """The Rules with this key, e.g. a game log's, or None if none has it."""
    return next((rules for rules in RULES.values() if rules.key == key), None)


__all__ = ["CHAOS", "RULES", "STANDARD", "Rules", "rules_named"]
