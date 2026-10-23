"""Converting a rating from Lichess Rapid to chess.com Rapid, the scale everything on the analytics page is given on.

The table is ChessGoals' rating comparison (https://www.chessgoals.com/rating-comparison/, updated July 2026: surveys
of active players, chess.com Rapid N = 10,156, Lichess Rapid N = 1,066), as quoted in docs/research/elo-estimation.md
section 3. Its windows of ±115 (chess.com Rapid) and ±90 (Lichess Rapid) hold "roughly 50% of players".

The table has no rows below Lichess Rapid 1290 (chess.com Rapid 815), and that is where our LLMs play: Maia-2's
lowest rating, Lichess 1000, is well below it. There the conversion goes on along the lowest row pair's line (and above
the table along the highest's), and its uncertainty grows with the distance from the table."""

from collections.abc import Sequence

# (Lichess Rapid, chess.com Rapid), ascending. ChessGoals' rows for chess.com Blitz 500, 800, 1000, 1200 and 1500.
LICHESS_RAPID_TO_CHESS_COM_RAPID: Sequence[tuple[int, int]] = (
    (1290, 815),
    (1490, 1085),
    (1615, 1255),
    (1740, 1420),
    (1905, 1655),
)
# The uncertainty a conversion adds inside the table, on the chess.com scale: about ±100 (the research's reading of
# ChessGoals' ±90-115 windows).
CONVERSION_MARGIN = 100.0
# Outside the table the margin grows by this much per Lichess point of extrapolation, so Lichess 1000 (290 below the
# table) carries ±245 rather than ±100. A judgement, not a measurement: there is no data to fit it to.
EXTRAPOLATION_MARGIN_PER_POINT = 0.5
CHESS_COM_MINIMUM = 100  # chess.com ratings don't go below 100


def lichess_floor() -> int:
    """The lowest Lichess Rapid rating the table covers (chess.com Rapid 815)."""
    return LICHESS_RAPID_TO_CHESS_COM_RAPID[0][0]


def lichess_ceiling() -> int:
    return LICHESS_RAPID_TO_CHESS_COM_RAPID[-1][0]


def chess_com_rapid(lichess_rapid: float) -> float:
    """The chess.com Rapid rating of a Lichess Rapid rating: linear between the table's rows, extended along its first
    and last segments outside it, and never below chess.com's minimum."""
    table = LICHESS_RAPID_TO_CHESS_COM_RAPID
    segment = next((index for index in range(len(table) - 2) if lichess_rapid < table[index + 1][0]), len(table) - 2)
    (x0, y0), (x1, y1) = table[segment], table[segment + 1]
    return max(float(CHESS_COM_MINIMUM), y0 + (lichess_rapid - x0) * (y1 - y0) / (x1 - x0))


def conversion_margin(lichess_rapid: float) -> float:
    """How far a chess.com Rapid rating converted from lichess_rapid may be off, on the chess.com scale."""
    outside = max(0.0, lichess_floor() - lichess_rapid, lichess_rapid - lichess_ceiling())
    return CONVERSION_MARGIN + EXTRAPOLATION_MARGIN_PER_POINT * outside


def is_extrapolated(lichess_rapid: float) -> bool:
    return not lichess_floor() <= lichess_rapid <= lichess_ceiling()
