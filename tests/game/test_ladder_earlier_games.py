"""The ladder resumes from the logged Anchor matches of the same Player configuration, an LLM's or a System 1 model's."""

from chessllm.analytics.leaderboard import system1_side_configuration
from chessllm.game.ladder import AnchoredGame, earlier_games
from chessllm.game.sides import System1Side
from tests.analytics.test_leaderboard import ANCHOR, D3, LLAMA, game, write_log

RANDOM_MOVER = {"player": "anchor", "engine": "random", "seed": 7}


def test_a_system_1_models_ladder_goes_on_from_its_logged_games_of_the_same_player_configuration(tmp_path):
    games = [
        game(D3, ANCHOR, "1-0", mode="anchor_match"),  # white wins against Skill 1
        game(RANDOM_MOVER, D3, "1-0", mode="anchor_match"),  # black loses to the random mover
        game(D3 | {"choice_temperature": 0.5}, ANCHOR, "1-0", mode="anchor_match"),  # another configuration
        game(LLAMA, ANCHOR, "1-0", mode="anchor_match"),  # an LLM's
        game(D3, ANCHOR, "1/2-1/2", mode="llm_faceoff"),  # not an Anchor match
    ]
    for number, events in enumerate(games):
        write_log(tmp_path, f"2026-10-19T10-00-{number:02d}_game", events)
    configuration = system1_side_configuration(System1Side(model="d3:9b", base_url="http://localhost:11434"), "standard")

    assert earlier_games(tmp_path, configuration) == [
        AnchoredGame(rung=1, llm_color="white", score=1.0),
        AnchoredGame(rung=0, llm_color="black", score=0.0),
    ]
