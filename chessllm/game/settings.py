"""The setup of one game and its checks: its Mode checks its sides, its Rules what they need of each side."""

from dataclasses import dataclass, field

from chessllm.core.types import COLORS, Color, ModeKey, RulesKey, Sampling
from chessllm.engines.anchors import DRAGON_SKILLS
from chessllm.exceptions import InvalidSettings
from chessllm.game.llm_turn.prompt import check_prompt_template, check_turn_memory, side_template
from chessllm.game.modes import MODES, Mode
from chessllm.game.rules import RULES, Rules
from chessllm.game.sides import AnchorSide, BenchmarkLlmSide, HumanSide, LlmSide, Side
from chessllm.llm.models import CONTEXT_TOKENS, THINKING_BUDGET_RANGE, LlmModel

# How many illegal moves an LLM may make in one turn before it forfeits: one attempt, the rest retries.
MAX_ATTEMPTS_RANGE = range(1, 26)


@dataclass(frozen=True)
class Settings:
    """The setup of one game, copied into it when it starts. Sampling is shared by every LLM side. The Mode and the
    Rules are given by their keys, as the API and the game log give them."""

    mode: ModeKey = "play_llm"
    white: Side = HumanSide()
    black: Side = LlmSide()
    sampling: Sampling = field(default_factory=dict)  # from the config file; empty means the model's defaults
    rules: RulesKey = "standard"  # one value for the whole game, applying to every LLM in it
    max_attempts: int = 5  # per LLM turn; after this many illegal moves the LLM forfeits
    # Under Chaos rules, whether each chaos move's Legal counterpart is asked for; Standard rules ignore it. Not part
    # of the Player configuration: the moves played are the same either way.
    legal_counterpart: bool = True

    def the_mode(self) -> Mode:
        """The Mode its key names."""
        return MODES[self.mode]

    def the_rules(self) -> Rules:
        """The Rules its key names."""
        return RULES[self.rules]

    def side(self, color: Color) -> Side:
        return self.white if color == "white" else self.black

    def llm_sides(self) -> dict[Color, LlmSide]:
        return {color: side for color in COLORS if isinstance(side := self.side(color), LlmSide)}

    def anchor_sides(self) -> dict[Color, AnchorSide]:
        return {color: side for color in COLORS if isinstance(side := self.side(color), AnchorSide)}

    def side_names(self) -> tuple[str, str]:
        """Who plays White and who plays Black, as the game log's file name has them: "human", the model, or the
        Anchor, e.g. "dragon-skill1"."""

        def name(side: Side) -> str:
            if isinstance(side, LlmSide):
                return side.model
            return side.file_name() if isinstance(side, AnchorSide) else "human"

        return name(self.white), name(self.black)

    def check(self, models: list[LlmModel]) -> None:
        """Raises InvalidSettings, saying why, if a game can't be played with these settings."""
        rules = self.the_rules()
        self.the_mode().check_sides(self.white, self.black)
        for color, anchor in self.anchor_sides().items():
            if anchor.skill not in DRAGON_SKILLS:
                low, high = DRAGON_SKILLS[0], DRAGON_SKILLS[-1]
                skills = f"Skill {low}-{high}"
                raise InvalidSettings(f"{anchor.engine.capitalize()} ({color}) plays at {skills}, not {anchor.skill}")
        if self.max_attempts not in MAX_ATTEMPTS_RANGE:
            low, high = MAX_ATTEMPTS_RANGE[0], MAX_ATTEMPTS_RANGE[-1]
            raise InvalidSettings(f"An LLM gets {low}-{high} attempts per turn, not {self.max_attempts}")
        for anchor in self.anchor_sides().values():
            rules.check_anchor(anchor)
        for color, side in self.llm_sides().items():
            model = next((model for model in models if model.name == side.model), None)
            if model is None:
                raise InvalidSettings(f"{side.model} ({color}) is not in the model list")
            if isinstance(side, BenchmarkLlmSide) and (level := side.thinking_level) is not None:
                if not model.thinking:
                    raise InvalidSettings(f"{side.model} ({color}) cannot think, so it has no Thinking levels")
                if not model.thinking_levels:
                    raise InvalidSettings(f"{side.model} ({color}) has no Thinking levels, only thinking on or off")
                if level not in model.thinking_levels:
                    offered = ", ".join(model.thinking_levels)
                    raise InvalidSettings(f"{side.model} ({color}) has no Thinking level {level}: it offers {offered}")
                if not side.thinking:
                    raise InvalidSettings(f"{side.model} ({color}) has Thinking level {level}, so thinking must be on")
            if side.thinking and not model.thinking:
                raise InvalidSettings(f"{side.model} ({color}) cannot think, so thinking must be off")
            if isinstance(side, BenchmarkLlmSide) and (budget := side.thinking_budget) is not None:
                low, high = THINKING_BUDGET_RANGE[0], THINKING_BUDGET_RANGE[-1]
                has_budget = f"{side.model} ({color}) has a Thinking budget"
                if not side.thinking:
                    raise InvalidSettings(f"{has_budget}, so thinking must be on")
                of_tokens = f"{has_budget} of {budget} tokens"
                if budget < low:
                    raise InvalidSettings(f"{of_tokens}, too few to hold an answer: at least {low}")
                if budget > high:
                    context = f"{CONTEXT_TOKENS:,}-token context"
                    raise InvalidSettings(f"{of_tokens}, too many for its {context}: at most {high}")
                if model.tokens_per_s is None:
                    raise InvalidSettings(f"{has_budget}, but no measured speed to set its time limit from")
            rules.check_llm(color, side)
            try:
                check_prompt_template(side_template(side), side.llm_constraints)
                check_turn_memory(side_template(side), side)
            except InvalidSettings as refused:
                raise InvalidSettings(f"{side.model} ({color}): {refused}", code=refused.code) from None
