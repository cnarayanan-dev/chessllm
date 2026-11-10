import pytest

from chessllm.exceptions import InvalidSettings
from chessllm.game.settings import Settings
from chessllm.game.sides import AnchorSide, BenchmarkLlmSide, HumanSide, LlmSide
from chessllm.llm.models import KNOWN_MODELS, LLM_MODELS

HAIKU = "claude-haiku-5-5"


def play(side: LlmSide, **settings) -> Settings:
    return Settings("play_llm", HumanSide(), side, **settings)


@pytest.mark.parametrize("thinking", [False, True])
@pytest.mark.parametrize("constraints", ["free", "listed", "blind_enforced", "listed_enforced"])
@pytest.mark.parametrize("memory", ["fresh", "chat_position"])
def test_a_hosted_model_plays_with_thinking_on_or_off_under_every_llm_constraints_and_turn_memory(
    thinking, constraints, memory
):
    side = LlmSide(model=HAIKU, thinking=thinking, llm_constraints=constraints, turn_memory=memory)

    play(side).check(KNOWN_MODELS)


def test_a_hosted_model_plays_under_chaos_rules_and_any_retry_feedback():
    side = LlmSide(model=HAIKU, retry_feedback="hinted")

    play(side, rules="chaos").check(KNOWN_MODELS)


def test_a_hosted_model_plays_in_a_faceoff_and_an_anchor_match():
    Settings("llm_faceoff", LlmSide(model=HAIKU), LlmSide(model="llama3:8b")).check(KNOWN_MODELS)
    Settings("anchor_match", LlmSide(model=HAIKU), AnchorSide.random_mover(seed=3)).check(KNOWN_MODELS)


def test_a_hosted_model_is_not_in_the_list_the_local_models_make():
    with pytest.raises(InvalidSettings, match=f"{HAIKU} .black. is not in the model list"):
        play(LlmSide(model=HAIKU)).check(LLM_MODELS)


@pytest.mark.parametrize(
    ("setting", "kwargs"),
    [
        ("Thinking level", {"thinking": True, "thinking_level": "high"}),
        ("Thinking budget", {"thinking": True, "thinking_budget": 1024}),
        ("Tools", {"thinking": True, "tools": frozenset({"board"})}),
    ],
)
def test_a_hosted_model_takes_no_thinking_level_thinking_budget_or_tools(setting, kwargs):
    with pytest.raises(InvalidSettings, match=rf"{HAIKU} \(black\) is a Hosted model, so it has no {setting}"):
        play(BenchmarkLlmSide(model=HAIKU, **kwargs)).check(KNOWN_MODELS)


def test_a_hosted_model_is_refused_without_access_to_its_provider():
    settings = Settings("llm_faceoff", LlmSide(model=HAIKU), LlmSide(model="llama3:8b"))

    with pytest.raises(InvalidSettings, match=rf"{HAIKU} \(white\).*CLAUDE_TOKEN") as refused:
        settings.check_hosted_access(False)

    assert refused.value.code == "hosted_model_unavailable"
    settings.check_hosted_access(True)


def test_games_of_local_models_need_no_access():
    Settings("llm_faceoff", LlmSide(), LlmSide(model="gemma3:12b")).check_hosted_access(False)
