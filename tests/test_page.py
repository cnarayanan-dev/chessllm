import re

import pytest


@pytest.fixture
def client(scripted):
    client, _ = scripted([])
    return client


def test_the_page_is_served_with_the_merida_credit(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Pieces: Merida by Armando Hernandez Marroquin, GPLv2+" in response.text


def test_the_merida_sprite_has_every_piece_cm_chessboard_expects(client):
    response = client.get("/static/pieces/merida.svg")

    assert response.status_code == 200
    ids = set(re.findall(r'<g id="([wb][kqrbnp])"', response.text))
    assert ids == {c + p for c in "wb" for p in "kqrbnp"}


def test_the_moves_card_has_the_show_llm_mistakes_switch_and_the_callout_stack_is_gone(client):
    page = client.get("/").text

    assert 'id="showMistakes"' in page
    assert "Show LLM mistakes" in page
    assert 'id="callouts"' not in page


def test_the_settings_modal_offers_the_llm_constraints(client):
    page = client.get("/").text

    assert 'id="llmConstraints"' in page
    assert "LLM constraints" in page


def test_the_settings_modal_offers_the_enforced_constraints_and_greys_out_retry_feedback_for_them(client):
    page = client.get("/").text

    assert "blind_enforced: {name: \"Blind enforced\"" in page
    assert "listed_enforced: {name: \"Listed enforced\"" in page
    assert ".radio:disabled" in page


def test_the_page_starts_the_llm_turn_with_its_own_request(client):
    page = client.get("/").text

    assert '"/api/games/current/llm-turn"' in page


def test_the_board_flashes_an_llm_turns_illegal_tries_forfeit_and_notation_slip_for_7_seconds(client):
    page = client.get("/").text

    assert 'id="boardWrap"' in page
    assert "LLM move illegal" in page
    assert "LLM forfeits: ${illegal.length} illegal moves" in page
    assert "of 4" in page
    assert "square-ring" in page and "bubble" in page
    assert "flash-out .4s ease-in 7s forwards" in page
