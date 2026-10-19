"""The React app's build, served at /next while the old page stays at / (#29)."""


def test_next_says_how_to_build_the_frontend_when_the_build_is_missing(scripted, tmp_path):
    client, _ = scripted([], dist_dir=tmp_path / "no-dist")

    response = client.get("/next")

    assert response.status_code == 503
    assert "pnpm install && pnpm build" in response.text
    assert "frontend/" in response.text


def test_next_serves_the_build_and_the_old_page_stays_at_the_root(scripted, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>ChessLLM next</title>")
    client, _ = scripted([], dist_dir=dist)

    response = client.get("/next")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<title>ChessLLM next</title>" in response.text
    assert "Pieces: Merida by Armando Hernandez Marroquin, GPLv2+" in client.get("/").text
