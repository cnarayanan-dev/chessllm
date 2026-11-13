from chessllm.core.config import CLAUDE_TOKEN_VARIABLE, claude_token_from_environment, load_environment


def test_the_token_is_none_without_one(monkeypatch):
    monkeypatch.delenv(CLAUDE_TOKEN_VARIABLE, raising=False)

    assert claude_token_from_environment() is None


def test_an_empty_token_is_none(monkeypatch):
    monkeypatch.setenv(CLAUDE_TOKEN_VARIABLE, "")

    assert claude_token_from_environment() is None


def test_the_token_is_read_when_asked_so_a_change_to_the_environment_applies(monkeypatch):
    monkeypatch.setenv(CLAUDE_TOKEN_VARIABLE, "first")
    assert claude_token_from_environment() == "first"

    monkeypatch.setenv(CLAUDE_TOKEN_VARIABLE, "second")
    assert claude_token_from_environment() == "second"


def test_the_token_can_come_from_an_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv(CLAUDE_TOKEN_VARIABLE, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(f"{CLAUDE_TOKEN_VARIABLE}=from-the-file\n", encoding="utf-8")

    load_environment(env_file)

    assert claude_token_from_environment() == "from-the-file"


def test_a_real_environment_variable_wins_over_the_env_file(tmp_path, monkeypatch):
    monkeypatch.setenv(CLAUDE_TOKEN_VARIABLE, "from-the-environment")
    env_file = tmp_path / ".env"
    env_file.write_text(f"{CLAUDE_TOKEN_VARIABLE}=from-the-file\n", encoding="utf-8")

    load_environment(env_file)

    assert claude_token_from_environment() == "from-the-environment"


def test_a_missing_env_file_is_no_error(tmp_path):
    load_environment(tmp_path / "no-such.env")


def test_a_stray_quote_or_space_around_the_token_is_dropped(monkeypatch):
    monkeypatch.setenv(CLAUDE_TOKEN_VARIABLE, ' sk-ant-token"\n')

    assert claude_token_from_environment() == "sk-ant-token"


def test_a_token_of_only_quotes_and_spaces_is_none(monkeypatch):
    monkeypatch.setenv(CLAUDE_TOKEN_VARIABLE, " \"' ")

    assert claude_token_from_environment() is None


def test_a_token_with_a_stray_quote_in_the_env_file_still_works(tmp_path, monkeypatch):
    monkeypatch.delenv(CLAUDE_TOKEN_VARIABLE, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(f'{CLAUDE_TOKEN_VARIABLE}=sk-ant-token"\n', encoding="utf-8")

    load_environment(env_file)

    assert claude_token_from_environment() == "sk-ant-token"
