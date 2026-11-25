from decimal import Decimal
from unittest import TestCase

from planner.domain import Candidate, PlanningError, Station
from planner.optimizer import optimize


def stop(identifier, mile, price, access=0):
    station = Station(identifier, identifier, "", "", "TX", Decimal(price), (0, 0), "station")
    return Candidate(station, mile, access, (0, 0))


class OptimizerTests(TestCase):
    def test_exact_range_needs_no_purchase(self):
        self.assertEqual(optimize(500, []), [])

    def test_cheaper_reachable_station_and_partial_purchase(self):
        cheap = stop("cheap", 380, "2.50")
        expensive = stop("expensive", 470, "4.00")
        plan = optimize(750, [expensive, cheap])
        self.assertEqual([purchase.candidate for purchase in plan], [cheap])
        self.assertEqual(plan[0].gallons, Decimal("25"))
        self.assertEqual(plan[0].cost, Decimal("62.50"))

    def test_purchase_only_enough_to_reach_even_cheaper_fuel(self):
        first = stop("first", 350, "3")
        second = stop("second", 700, "2")
        plan = optimize(1100, [second, first])
        self.assertEqual([purchase.candidate for purchase in plan], [first, second])
        self.assertEqual([purchase.gallons for purchase in plan], [Decimal(20), Decimal(40)])

    def test_access_miles_affect_reachability(self):
        with self.assertRaises(PlanningError) as result:
            optimize(700, [stop("too far", 495, "1", access=6)])
        self.assertEqual(result.exception.code, "no_feasible_fuel_plan")

    def test_round_trip_access_is_included_in_purchase(self):
        plan = optimize(700, [stop("fuel", 370, "2", access=5)])
        self.assertEqual(plan[0].gallons, Decimal(21))

    def test_equal_prices_prefers_fewer_stops(self):
        # All three stops cost the same. Only the middle one can finish the
        # first leg and fit the rest of the trip in a single top-up.
        candidates = [stop("early", 100, "3"), stop("middle", 420, "3"), stop("late", 600, "3")]
        plan = optimize(850, candidates)
        self.assertEqual([purchase.candidate.station.id for purchase in plan], ["middle"])
