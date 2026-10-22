"""The Rating: each Player configuration's Elo on the chess.com Rapid scale, fitted only from results (ADR 0005).

One maximum-likelihood fit over a pool of every rated game, recalculated from the games on each call, so the order
they were played in doesn't matter and there is no rating state to store. The model is the logistic Elo model
(Bradley-Terry on a 400-point base-10 scale) with a draw counted as half a point: a player rated r scores
1 / (1 + 10^((r_o - r) / 400)) against one rated r_o, and a game scored s contributes s·log p + (1 - s)·log(1 - p).
Anchors are free parameters too, each with a Gaussian prior at its rating ± its uncertainty, which is what puts the
fit on the chess.com scale; Player configurations have no prior. There is no first-move term: Anchor match batches
alternate colours.

Who can be rated follows from the direction of the results. Count an edge from u to v when u scored against v (won or
drew); the Anchors, tied together by their priors, count as one node. A finite maximum exists exactly for the
configurations in the Anchors' strongly connected component: they scored against something that leads back to the
Anchors, and something that leads from the Anchors scored against them. That component is fitted by Newton's method,
and its 95% intervals come from the inverse of the observed Fisher information (the negative Hessian) at the maximum.

- Reachable from the Anchors but not leading back (for example, it lost every game to Dragon): the likelihood keeps
  rising as its rating falls, so there is only an upper bound "< X": the rating at which results this bad would have
  had a 5% chance. Its opponents are taken at their fitted ratings, or their own upper bounds.
- Leading to the Anchors but not reachable from them (it won every game): a lower bound "> X", by symmetry.
- Neither (faceoffs only, or only an unrated path): no Rating.
"""

import math
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from pydantic import BaseModel

from chessllm.engines.anchors import AnchorRating

Z_95 = 1.959963984540054  # two-sided 95% interval: estimate ± Z_95 standard errors
BOUND_CHANCE = 0.05  # a one-sided 95% bound
ELO_SCALE = 400 / math.log(10)  # p = 1 / (1 + exp(-(r - r_o) / ELO_SCALE))
ANCHORS = "anchors"  # the node all Anchors make together in the graph of results


class Rating(BaseModel):
    """A Player configuration's Rating on the chess.com Rapid scale, fitted only from rated results. Never blended
    with the Move-quality estimate. Either an estimate with its 95% interval, an upper bound ("< high", estimate and
    low None) or a lower bound ("> low", estimate and high None)."""

    estimate: int | None  # the maximum-likelihood rating; None when only a bound is known
    low: int | None  # the 95% interval's lower end, or the lower bound; None when open below ("< high")
    high: int | None  # the 95% interval's upper end, or the upper bound; None when open above ("> low")
    rated_games: int  # its games in the pool: Anchor matches and LLM faceoffs under Standard rules


@dataclass(frozen=True)
class RatedGame:
    """One rated game between two players, each a Player configuration's id or an Anchor's name."""

    white: str
    black: str
    white_score: float  # 1, 0.5 or 0


def ratings(games: Iterable[RatedGame], anchors: Mapping[str, AnchorRating]) -> dict[str, Rating]:
    """The Rating of every player in the games that isn't an Anchor and can be rated; the rest are left out.

    Games against an Anchor missing from anchors, and a configuration's games against itself, carry no information
    about the scale and are left out."""
    pool = sorted(
        (game.white, game.black, game.white_score)
        for game in games
        if game.white != game.black
        and all(player in anchors or not is_anchor(player) for player in (game.white, game.black))
    )
    counts: dict[str, int] = defaultdict(int)
    scored: dict[str, set[str]] = defaultdict(set)  # u -> every v that u scored against, Anchors as one node
    for white, black, score in pool:
        counts[white] += 1
        counts[black] += 1
        white_node, black_node = (ANCHORS if player in anchors else player for player in (white, black))
        if score > 0:
            scored[white_node].add(black_node)
        if score < 1:
            scored[black_node].add(white_node)
    scored_by: dict[str, set[str]] = defaultdict(set)
    for winner, losers in scored.items():
        for loser in losers:
            scored_by[loser].add(winner)

    below = reachable(ANCHORS, scored)  # the Anchors (or what they lead to) scored against them: bounded above
    above = reachable(ANCHORS, scored_by)  # they lead to the Anchors: bounded below
    core = below & above
    values: dict[str, float] = {}
    result: dict[str, Rating] = {}

    if ANCHORS in core:
        members = sorted(core - {ANCHORS})
        anchors_played = sorted({player for game in pool for player in game[:2] if player in anchors})
        estimates, covariance = fit(members + anchors_played, {}, pool, anchors)
        values.update(estimates)
        for index, player in enumerate(members):
            error = Z_95 * math.sqrt(covariance[index][index])
            estimate = estimates[player]
            result[player] = Rating(
                estimate=round(estimate),
                low=round(estimate - error),
                high=round(estimate + error),
                rated_games=counts[player],
            )

    def node(player: str) -> str:
        return ANCHORS if player in anchors else player

    for region, known_from, sign in ((below - core, scored_by, 1), (above - core, scored, -1)):
        # Upper bounds build on the fit and each other, lower bounds likewise, never one on the other.
        for player, bound in bounds(region, known_from, dict(values), pool, sign, node).items():
            upper = sign > 0
            result[player] = Rating(
                estimate=None,
                low=None if upper else round(bound),
                high=round(bound) if upper else None,
                rated_games=counts[player],
            )
    return result


def is_anchor(player: str) -> bool:
    return player.startswith("anchor:")


def reachable(start: str, edges: Mapping[str, set[str]]) -> set[str]:
    seen, stack = {start}, [start]
    while stack:
        for following in edges.get(stack.pop(), ()):
            if following not in seen:
                seen.add(following)
                stack.append(following)
    return seen


def expected_score(difference: float) -> float:
    """The expected score of a player rated difference points above the opponent."""
    return 1 / (1 + math.exp(-max(-20_000.0, min(20_000.0, difference)) / ELO_SCALE))


def bounds(
    region: set[str],
    known_from: Mapping[str, set[str]],
    values: dict[str, float],
    pool: list[tuple[str, str, float]],
    sign: int,
    node: Callable[[str], str],
) -> dict[str, float]:
    """The one-sided 95% bound of every player in region: upper bounds for sign 1, lower bounds for sign -1.

    known_from gives, for each player, those whose results bound it (who scored against it for an upper bound, who it
    scored against for a lower one). The region's strongly connected components are bounded one at a time, each once
    every component bounding it is done; within a component, the players keep their fitted differences and are shifted
    together until the results against known opponents had a 5% chance. values gains every bound found. node names
    a player's node in known_from (all Anchors are one)."""
    found: dict[str, float] = {}
    components = strongly_connected(region, known_from)
    pending = sorted(components, key=min)
    while pending:
        component = next(
            c
            for c in pending
            if all(other in values or other in c or other not in region for p in c for other in known_from.get(p, ()))
        )
        pending.remove(component)
        members = sorted(component)
        inside = [game for game in pool if game[0] in component and game[1] in component]
        differences, _ = fit(members[1:], {members[0]: 0.0}, inside, {})
        # Each result against a known opponent: (the member's fitted difference, the opponent's value)
        known = [
            (differences[player], values[opponent])
            for white, black, _ in pool
            for player, opponent in ((white, black), (black, white))
            if player in component and opponent in values and node(opponent) in known_from.get(player, ())
        ]

        def chance(shift: float) -> float:
            # sign 1: the chance of losing every one of them; sign -1: of winning every one
            return sum(math.log(expected_score(sign * (value - difference - shift))) for difference, value in known)

        shift = solve(lambda shift: chance(shift) - math.log(BOUND_CHANCE), -20_000.0, 20_000.0)
        for player in members:
            values[player] = found[player] = differences[player] + shift
    return found


def strongly_connected(region: set[str], edges: Mapping[str, set[str]]) -> list[frozenset[str]]:
    inside = {player: edges.get(player, set()) & region for player in region}
    reach = {player: reachable(player, inside) for player in region}
    return list({frozenset(other for other in reach[player] if player in reach[other]) for player in region})


def solve(function: Callable[[float], float], low: float, high: float) -> float:
    """A root of a monotonic function between low and high, by bisection."""
    rising = function(high) > function(low)
    for _ in range(200):
        middle = (low + high) / 2
        if (function(middle) < 0) == rising:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def fit(
    free: list[str],
    fixed: Mapping[str, float],
    pool: list[tuple[str, str, float]],
    priors: Mapping[str, AnchorRating],
) -> tuple[dict[str, float], list[list[float]]]:
    """The maximum a posteriori ratings of the free players, by Newton's method, with the covariance of the free
    ones (the inverse of the negative Hessian). Fixed players keep their ratings; players with a prior are pulled
    towards it. Only games between the given players count."""
    index = {player: number for number, player in enumerate(free)}
    start = sum(prior.rating for prior in priors.values()) / len(priors) if priors else 0.0
    x = [priors[player].rating if player in priors else start for player in free]
    games = [game for game in pool if all(player in index or player in fixed for player in game[:2])]

    def rating(player: str, x: list[float]) -> float:
        return x[index[player]] if player in index else fixed[player]

    def log_posterior(x: list[float]) -> float:
        total = 0.0
        for white, black, score in games:
            p = expected_score(rating(white, x) - rating(black, x))
            total += score * math.log(max(p, 1e-300)) + (1 - score) * math.log(max(1 - p, 1e-300))
        for player, number in index.items():
            if player in priors:
                total -= ((x[number] - priors[player].rating) / priors[player].uncertainty) ** 2 / 2
        return total

    def derivatives(x: list[float]) -> tuple[list[float], list[list[float]]]:
        gradient = [0.0] * len(x)
        hessian = [[0.0] * len(x) for _ in x]
        for white, black, score in games:
            p = expected_score(rating(white, x) - rating(black, x))
            slope, curvature = (score - p) / ELO_SCALE, p * (1 - p) / ELO_SCALE**2
            for player, side in ((white, 1), (black, -1)):
                if player in index:
                    gradient[index[player]] += side * slope
                    hessian[index[player]][index[player]] -= curvature
            if white in index and black in index:
                hessian[index[white]][index[black]] += curvature
                hessian[index[black]][index[white]] += curvature
        for player, number in index.items():
            if player in priors:
                gradient[number] -= (x[number] - priors[player].rating) / priors[player].uncertainty ** 2
                hessian[number][number] -= 1 / priors[player].uncertainty ** 2
        return gradient, hessian

    for _ in range(100):
        gradient, hessian = derivatives(x)
        step = solve_linear([[-value for value in row] for row in hessian], gradient)
        current, scale = log_posterior(x), 1.0
        while scale > 1e-6 and log_posterior([a + scale * b for a, b in zip(x, step)]) < current:
            scale /= 2
        x = [a + scale * b for a, b in zip(x, step)]
        if max((abs(b) * scale for b in step), default=0.0) < 1e-7:
            break
    _, hessian = derivatives(x)
    negative = [[-value for value in row] for row in hessian]
    covariance = [solve_linear(negative, [float(i == j) for j in range(len(x))]) for i in range(len(x))]
    return {player: x[number] for player, number in index.items()} | dict(fixed), covariance


def solve_linear(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """x with matrix · x = vector, by Gaussian elimination with partial pivoting. The matrix must be invertible."""
    size = len(vector)
    rows = [[*row, value] for row, value in zip(matrix, vector)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(rows[row][column]))
        rows[column], rows[pivot] = rows[pivot], rows[column]
        for row in range(column + 1, size):
            factor = rows[row][column] / rows[column][column]
            for k in range(column, size + 1):
                rows[row][k] -= factor * rows[column][k]
    solution = [0.0] * size
    for row in reversed(range(size)):
        known = sum(rows[row][k] * solution[k] for k in range(row + 1, size))
        solution[row] = (rows[row][size] - known) / rows[row][row]
    return solution
