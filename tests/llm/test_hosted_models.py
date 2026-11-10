from chessllm.core.config import CLAUDE_TOKEN_VARIABLE
from chessllm.llm.models import HOSTED_MODELS, KNOWN_MODELS, LLM_MODELS, context_tokens, offered_models


def test_claude_haiku_5_5_is_the_one_hosted_model_and_can_think_on_or_off():
    [haiku] = HOSTED_MODELS

    assert haiku.name == "claude-haiku-5-5"
    assert haiku.hosted
    assert haiku.thinking_values == (False, True)
    assert haiku.thinking_levels == ()  # a Hosted model has no Thinking levels, budget or Tools
    assert haiku.tokens_per_s is None
    assert not haiku.tools


def test_no_local_model_is_hosted():
    assert not any(model.hosted for model in LLM_MODELS)
    assert KNOWN_MODELS == [*LLM_MODELS, *HOSTED_MODELS]


def test_without_a_token_only_the_local_models_are_offered():
    assert offered_models() == LLM_MODELS


def test_with_a_token_the_hosted_models_are_offered_after_the_local_ones(monkeypatch):
    monkeypatch.setenv(CLAUDE_TOKEN_VARIABLE, "a-token")

    assert offered_models() == [*LLM_MODELS, *HOSTED_MODELS]


def test_a_hosted_model_has_a_context_of_its_own_and_a_local_one_ollamas():
    assert context_tokens("llama3:8b") is None  # Ollama's CONTEXT_TOKENS
    assert context_tokens("no-such-model") is None
    assert context_tokens("claude-haiku-5-5") == 1_000_000
