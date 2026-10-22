"""The React app's build (frontend/, `pnpm build`) served at /, and the static files it loads (#37). A build made for
a different API is refused (#80)."""

import re

from scripts.generate_api_types import SCHEMA_FILE

# The fingerprint of the API description the committed schema.ts was generated from, which a build made from it carries.
CURRENT_FINGERPRINT = SCHEMA_FILE.read_text(encoding="utf-8").splitlines()[0].rsplit(" ", 1)[1]
OTHER_FINGERPRINT = "0" * 64


def write_build(dist, fingerprint=CURRENT_FINGERPRINT):
    """A fake build: its index.html and, unless fingerprint is None, the API fingerprint it was made for."""
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>ChessLLM build</title>")
    if fingerprint is not None:
        (dist / "api-fingerprint.txt").write_text(f"{fingerprint}\n")
    return dist


def test_the_root_says_how_to_build_the_frontend_when_the_build_is_missing(scripted, tmp_path):
    client, _ = scripted([], dist_dir=tmp_path / "no-dist")

    response = client.get("/")

    assert response.status_code == 503
    assert "pnpm install && pnpm build" in response.text
    assert "frontend/" in response.text


def test_the_root_serves_the_build(scripted, tmp_path):
    client, _ = scripted([], dist_dir=write_build(tmp_path / "dist"))

    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<title>ChessLLM build</title>" in response.text


def test_the_analytics_page_serves_the_same_build(scripted, tmp_path):
    client, _ = scripted([], dist_dir=write_build(tmp_path / "dist"))

    response = client.get("/analytics")

    assert response.status_code == 200
    assert "<title>ChessLLM build</title>" in response.text


def test_a_build_made_for_a_different_api_is_refused_naming_both_fingerprints(scripted, tmp_path):
    client, _ = scripted([], dist_dir=write_build(tmp_path / "dist", OTHER_FINGERPRINT))

    for path in ["/", "/analytics"]:
        response = client.get(path)

        assert response.status_code == 503
        assert "pnpm build" in response.text
        assert OTHER_FINGERPRINT in response.text
        assert CURRENT_FINGERPRINT in response.text
        assert "<title>" not in response.text


def test_a_build_without_an_api_fingerprint_is_refused(scripted, tmp_path):
    client, _ = scripted([], dist_dir=write_build(tmp_path / "dist", None))

    response = client.get("/")

    assert response.status_code == 503
    assert "pnpm build" in response.text
    assert CURRENT_FINGERPRINT in response.text


def test_next_is_gone(scripted, tmp_path):
    client, _ = scripted([], dist_dir=tmp_path / "no-dist")

    assert client.get("/next").status_code == 404


def test_the_merida_sprite_has_every_piece_cm_chessboard_expects(scripted):
    client, _ = scripted([])

    response = client.get("/static/pieces/merida.svg")

    assert response.status_code == 200
    ids = set(re.findall(r'<g id="([wb][kqrbnp])"', response.text))
    assert ids == {c + p for c in "wb" for p in "kqrbnp"}


def test_the_move_sound_is_served(scripted):
    client, _ = scripted([])

    sound = client.get("/static/sounds/move.mp3")

    assert sound.status_code == 200
    assert sound.content.startswith(b"ID3")
