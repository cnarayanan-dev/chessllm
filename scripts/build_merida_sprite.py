"""Build the merida piece sprite that cm-chessboard expects from the Lichess merida SVGs.

cm-chessboard wants one SVG with a <g id="wk">, <g id="bq"> ... per piece on a 40-unit tile.
The Lichess files are 50 x 50 and all reuse the gradient id "a", so each piece is scaled
down and its ids are prefixed with the piece name.

Run: uv run python scripts/build_merida_sprite.py
Pieces: Merida by Armando Hernandez Marroquin, GPLv2+.
"""

import re
import urllib.request
from pathlib import Path

SOURCE = "https://raw.githubusercontent.com/lichess-org/lila/master/public/piece/merida/{}.svg"
TARGET = Path(__file__).parent.parent / "chessllm" / "static" / "pieces" / "merida.svg"
SOURCE_SIZE, TILE_SIZE = 50, 40

HEADER = """<?xml version="1.0" encoding="UTF-8"?>
<!--
Merida chess pieces by Armando Hernandez Marroquin, GPLv2+.
Taken from Lichess (https://github.com/lichess-org/lila/tree/master/public/piece/merida)
and combined into a cm-chessboard sprite by scripts/build_merida_sprite.py.
-->
<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 40 40">
"""


def piece_group(name: str, svg: str) -> str:
    sprite_id = name.lower()
    inner = re.sub(r"^.*?<svg[^>]*>|</svg>\s*$", "", svg, flags=re.DOTALL)
    inner = re.sub(r'id="([^"]+)"', rf'id="{sprite_id}-\1"', inner)
    inner = re.sub(r"url\(#([^)]+)\)", rf"url(#{sprite_id}-\1)", inner)
    inner = re.sub(r'href="#([^"]+)"', rf'href="#{sprite_id}-\1"', inner)
    return f'<g id="{sprite_id}" transform="scale({TILE_SIZE / SOURCE_SIZE})">{inner}</g>\n'


def main() -> None:
    groups = []
    for name in [c + p for c in "wb" for p in "KQRBNP"]:
        with urllib.request.urlopen(SOURCE.format(name)) as response:
            groups.append(piece_group(name, response.read().decode()))
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(HEADER + "".join(groups) + "</svg>\n")
    print(f"wrote {TARGET}")


if __name__ == "__main__":
    main()
