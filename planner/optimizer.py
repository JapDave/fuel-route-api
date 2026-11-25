"""Minimum purchase cost for a fixed route and estimated station access distances."""
from dataclasses import dataclass
from decimal import Decimal
from math import inf

from .domain import Candidate, MPG, PlanningError, RANGE_MILES

EPSILON = 1e-8


@dataclass(frozen=True)
class Purchase:
    candidate: Candidate
    fuel_miles: float

    @property
    def gallons(self) -> Decimal:
        return Decimal(str(round(self.fuel_miles, 10))) / MPG

    @property
    def cost(self) -> Decimal:
        return self.gallons * self.candidate.station.price


def optimize(distance: float, candidates: list[Candidate]) -> list[Purchase]:
    """Start full and minimize cash spent en route, breaking ties by stop count.

    In an optimal plan, between fuel purchases either the first departure is
    full or the next arrival is empty. Otherwise fuel can shift toward the
    cheaper stop until one of those boundaries is reached. With equal prices,
    shifting forward yields the same cost. An intermediate purchase between
    a full departure and an empty arrival is represented by a single edge.
    """
    if distance <= RANGE_MILES:
        return []

    ordered = sorted(candidates, key=lambda stop: (stop.mile, stop.station.id))
    miles = [0.0, *(stop.mile for stop in ordered), distance]
    access = [0.0, *(stop.access_miles for stop in ordered), 0.0]
    prices = [0.0, *(float(stop.station.price) for stop in ordered), 0.0]
    last = len(miles) - 1

    # At each station, even indices mean empty arrival and odd indices mean
    # full departure. The destination uses its arrival state for any fuel level.
    start, finish = 1, 2 * last
    best = [(inf, 0)] * (finish + 1)
    previous = [None] * len(best)
    best[start] = (0.0, 0)

    def relax(source, target, buyer=None, amount=0.0):
        if buyer is None or amount <= EPSILON:
            score = best[source]
            purchase = None
        else:
            score = (best[source][0] + amount * prices[buyer], best[source][1] + 1)
            purchase = Purchase(ordered[buyer - 1], amount)
        current = best[target]
        if score[0] < current[0] - EPSILON or (
            abs(score[0] - current[0]) <= EPSILON and score[1] < current[1]
        ):
            best[target] = score
            previous[target] = (source, purchase)

    def reachable(index):
        for next_index in range(index + 1, last + 1):
            along = miles[next_index] - miles[index] + access[index]
            if along > RANGE_MILES + EPSILON:
                break
            leg = along + access[next_index]
            if leg <= RANGE_MILES + EPSILON:
                yield next_index, leg

    neighbors = [list(reachable(index)) for index in range(last)]
    for index, edges in enumerate(neighbors):
        empty, full = 2 * index, 2 * index + 1
        if best[empty][0] < inf:
            relax(empty, full, index, RANGE_MILES)
            for target, leg in edges:
                relax(empty, 2 * target, index, leg)

        if best[full][0] == inf:
            continue
        for target, leg in edges:
            if target == last or leg >= RANGE_MILES - EPSILON:
                relax(full, 2 * target)
            if target == last:
                continue
            relax(full, 2 * target + 1, target, leg)

            for end, second_leg in neighbors[target]:
                refill = leg + second_leg - RANGE_MILES
                if refill > EPSILON:
                    relax(full, 2 * end, target, refill)

    if previous[finish] is None:
        raise PlanningError(
            "no_feasible_fuel_plan",
            "No sequence of catalog stations keeps every estimated leg within 500 miles.",
        )

    purchases = []
    node = finish
    while node != start:
        node, purchase = previous[node]
        if purchase is not None:
            purchases.append(purchase)
    return list(reversed(purchases))
