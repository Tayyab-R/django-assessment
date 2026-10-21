import json
import random
import unittest

import numpy as np

from app.matcher import NoFeasiblePlan
from app.optimizer import plan_fuel
from app.tests.helpers import candidates

FULL_TANK_GALLONS = 50


def exact_cost(pairs, total, tank_gal=50, mpg=10):
    """Exact answer by dynamic programming over whole gallons (slow but certain)."""
    nodes = [(0, None)] + sorted(pairs) + [(total, None)]
    best = {tank_gal: 0.0}
    for i in range(len(nodes) - 1):
        price = nodes[i][1]
        need = (nodes[i + 1][0] - nodes[i][0]) // mpg
        nxt = {}
        for fuel, cost in best.items():
            max_buy = (tank_gal - fuel) if price is not None else 0
            for buy in range(max_buy + 1):
                if fuel + buy >= need:
                    left = fuel + buy - need
                    c = cost + (buy * price if price is not None else 0)
                    if c < nxt.get(left, float("inf")):
                        nxt[left] = c
        best = nxt
    return min(best.values())


class WorkedExamples(unittest.TestCase):
    def test_cheapest_station_in_the_middle_gets_the_fuel(self):
        plan = plan_fuel(candidates([(100, 3.50), (300, 3.00), (450, 4.00)]), 700)
        self.assertEqual(len(plan.stops), 1)
        stop = plan.stops[0]
        self.assertEqual(stop.mile, 300)
        self.assertAlmostEqual(stop.gallons, 20.0)
        self.assertAlmostEqual(plan.total_cost, 60.0)

    def test_two_stops_when_the_early_station_is_cheaper(self):
        plan = plan_fuel(candidates([(100, 3.50), (300, 3.80), (450, 4.00)]), 700)
        self.assertEqual([s.mile for s in plan.stops], [100, 300])
        self.assertAlmostEqual(plan.stops[0].gallons, 10.0)   # top up at the cheap one
        self.assertAlmostEqual(plan.stops[1].gallons, 10.0)   # just enough to finish
        self.assertAlmostEqual(plan.total_cost, 73.0)

    def test_short_trip_needs_no_stops(self):
        plan = plan_fuel(candidates([(100, 3.50)]), 300)
        self.assertEqual(plan.stops, [])
        self.assertEqual(plan.total_cost, 0.0)

    def test_nothing_is_wasted(self):
        # fuel bought + the free starting tank == fuel the trip burns
        for pairs in ([(100, 3.50), (300, 3.00), (450, 4.00)], [(100, 3.50), (300, 3.80), (450, 4.00)]):
            plan = plan_fuel(candidates(pairs), 700)
            self.assertAlmostEqual(plan.gallons_purchased + FULL_TANK_GALLONS, plan.trip_gallons)

    def test_cheapest_of_several_stations_at_one_mile_is_used(self):
        # stations in the same city share a mile marker; only the cheapest matters
        plan = plan_fuel(candidates([(300, 3.90), (300, 3.10), (300, 3.50)]), 700)
        self.assertEqual(len(plan.stops), 1)
        self.assertAlmostEqual(plan.stops[0].price, 3.10)


class Feasibility(unittest.TestCase):
    def test_gap_longer_than_the_range_raises(self):
        with self.assertRaises(NoFeasiblePlan):
            plan_fuel(candidates([(700, 3.00)]), 1500)

    def test_results_are_plain_floats_that_serialize_to_json(self):
        plan = plan_fuel(candidates([(100, 3.50), (300, 3.80), (450, 4.00)]), 700)
        json.dumps([s.__dict__ for s in plan.stops])


class MatchesExactSolver(unittest.TestCase):
    def test_greedy_equals_dynamic_programming_on_random_trips(self):
        rng = random.Random(7)
        checked = 0
        while checked < 150:
            total = rng.randrange(600, 2000, 10)
            miles = sorted(rng.sample(range(0, total, 10), rng.randint(4, 15)))
            pairs = [(m, round(rng.uniform(2.5, 4.5), 2)) for m in miles]
            if np.diff([0] + miles + [total]).max() > 500:
                continue                                   # infeasible, skip
            checked += 1
            greedy = plan_fuel(candidates(pairs), total).total_cost
            self.assertAlmostEqual(greedy, exact_cost(pairs, total), places=6, msg=f"{pairs} {total}")


if __name__ == "__main__":
    unittest.main()
