"""Turn memory from the app: a new game takes each side's Turn memory, a Rematch keeps it, and the whole Prompt of
an attempt in a conversation is rebuilt from the game's records for the Turn panel (ADR 0009)."""

from tests.conftest import Raw, play_llm, play_move

import json

import pytest


def rematch_of(settings: dict) -> dict:
    """The rematch's new-game request as the page builds it: each side, with the settings it played under, takes the
    other colour."""
    return {"mode": settings["mode"], "white": settings["black"], "black": settings["white"]}


@pytest.mark.parametrize(
    ("turn_memory", "second_turn"),
    [
        ("fresh", ["system", "user"]),
        ("chat_position", ["system", "user", "assistant", "user"]),
        ("chat_moves", ["system", "user", "assistant", "user"]),
    ],
)
def test_a_new_game_plays_the_turn_memory_it_asks_for_and_a_rematch_keeps_it(
    scripted, tmp_path, turn_memory, second_turn
):
    client, player = scripted(["e5", "Nc6", "e5"])

    started = client.post("/api/games", json=play_llm(turn_memory=turn_memory))
    for uci in ["e2e4", "g1f3"]:
        assert play_move(client, uci).status_code == 200
    settings = client.get("/api/games/current").json()["settings"]
    [log] = (tmp_path / "games").glob("*.jsonl")
    game_start = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    rematch = client.post("/api/games", json=rematch_of(settings))

    assert started.status_code == 200, started.text
    assert [message.role for message in player.prompts[1]] == second_turn
    if turn_memory == "chat_moves":
        assert player.prompts[1][-1].content == "Opponent played Nf3."
    assert settings["black"]["turn_memory"] == turn_memory  # always in the state, as the API's schema says
    # Left out of the game log when fresh, so a fresh game logs as before Turn memory.
    assert game_start["black"].get("turn_memory") == (None if turn_memory == "fresh" else turn_memory)
    assert rematch.status_code == 200, rematch.text
    assert rematch.json()["settings"]["white"]["turn_memory"] == turn_memory


def play_out(client) -> dict:
    """Ask for LLM turns, as the page does in an LLM faceoff, until the game is over."""
    state = client.get("/api/games/current").json()
    while state["status"] == "playing":
        state = client.post("/api/games/current/llm-turn").json()
    return state


def prompt_of(client, ply: int, attempt: int):
    return client.get(f"/api/games/current/llm-turns/{ply}/attempts/{attempt}/prompt")


def as_sent(prompt: dict) -> list[tuple[str, str]]:
    """A rebuilt Prompt as the LLM received it: the System prompt, then each turn's messages."""
    messages = [prompt["system"], *(message for turn in prompt["turns"] for message in turn["messages"])]
    return [(message["role"], message["content"]) for message in messages]


def test_an_attempts_whole_prompt_in_a_conversation_is_rebuilt_by_turn_with_the_turns_trimmed_from_it(faceoff):
    # White's first answer is long, so by its fourth turn the conversation would pass the context: its first turn is
    # dropped whole (as in tests/game/test_conversation_trimming.py).
    long_answer = Raw(json.dumps({"reasoning": "x" * 9_000, "move": "Nc3"}))
    client, _, players = faceoff(
        [long_answer, "Nb1", "Nc3", "e3", "d3"], ["Nc6", "Nb8", "Nc6", "e6"], {"turn_memory": "chat_position"}
    )
    players["white"].usage = [{"prompt_tokens": tokens} for tokens in [1_000, 4_000, 7_650, 4_700, 4_760]]
    play_out(client)
    white = players["white"].prompts

    second, fourth = prompt_of(client, 3, 1).json(), prompt_of(client, 7, 1).json()

    assert (second["trimmed"], [turn["number"] for turn in second["turns"]]) == (0, [1, 2])
    assert (fourth["trimmed"], [turn["number"] for turn in fourth["turns"]]) == (1, [2, 3, 4])
    assert as_sent(second) == [(message.role, message.content) for message in white[1]]
    assert as_sent(fourth) == [(message.role, message.content) for message in white[3]]


def test_a_fresh_attempts_prompt_is_its_own_turn_and_an_attempt_the_game_has_not_played_has_none(scripted):
    client, player = scripted(["e5"])
    client.post("/api/games", json=play_llm())
    play_move(client, "e2e4")

    fresh = prompt_of(client, 2, 1).json()
    missing = [prompt_of(client, 2, 2), prompt_of(client, 1, 1), prompt_of(client, 4, 1)]

    assert (fresh["trimmed"], [turn["number"] for turn in fresh["turns"]]) == (0, [1])
    assert as_sent(fresh) == [(message.role, message.content) for message in player.prompts[0]]
    assert [(response.status_code, response.json()["code"]) for response in missing] == [(404, "no_llm_attempt")] * 3


def test_a_retry_that_had_to_drop_more_turns_than_its_first_attempt_is_rebuilt_with_them_trimmed(faceoff):
    # White's third turn's first answer is long and illegal: kept with its Retry feedback, it leaves too little room
    # for the retry's reply until the first turn is dropped (as in tests/game/test_conversation_trimming.py).
    long_illegal = Raw(json.dumps({"reasoning": "x" * 9_000, "move": "Qxf7"}))
    client, _, players = faceoff(
        ["Nc3", "Nb1", long_illegal, "Nc3", "e3"], ["Nc6", "Nb8", "Nc6"], {"turn_memory": "chat_position"}
    )
    players["white"].usage = [{"prompt_tokens": tokens} for tokens in [1_000, 1_600, 1_650, 7_600, 7_650]]
    play_out(client)
    white = players["white"].prompts

    first_attempt, retry = prompt_of(client, 5, 1).json(), prompt_of(client, 5, 2).json()

    assert (first_attempt["trimmed"], [turn["number"] for turn in first_attempt["turns"]]) == (0, [1, 2, 3])
    assert (retry["trimmed"], [turn["number"] for turn in retry["turns"]]) == (1, [2, 3])
    assert as_sent(first_attempt) == [(message.role, message.content) for message in white[2]]
    assert as_sent(retry) == [(message.role, message.content) for message in white[3]]
