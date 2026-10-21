import unittest

import numpy as np

from app.matcher import (NoFeasiblePlan, find_candidates, find_feasible_candidates,
                         max_gap, thin_route)
from app.tests.helpers import make_stations, meridian_route


class ThinRoute(unittest.TestCase):
    def test_about_one_point_per_mile_and_keeps_both_ends(self):
        route = meridian_route(1000)
        idx = thin_route(route)
        self.assertEqual(idx[0], 0)
        self.assertEqual(idx[-1], len(route.cum_miles) - 1)
        self.assertLess(len(idx), 1100)                        # thinned from 3,000 points
        self.assertLessEqual(np.diff(route.cum_miles[idx]).max(), 1.1)


class FindCandidates(unittest.TestCase):
    def setUp(self):
        self.route = meridian_route(500)
        self.stations = make_stations([(100, 3.5, 0), (200, 3.0, 4), (300, 3.2, 9)])

    def test_keeps_stations_inside_the_corridor_only(self):
        c = find_candidates(self.route, self.stations, corridor_miles=5)
        self.assertEqual(sorted(c.station_idx.tolist()), [0, 1])   # 9 miles off is out

    def test_mile_markers_and_distance_from_road(self):
        c = find_candidates(self.route, self.stations, corridor_miles=5)
        self.assertAlmostEqual(c.mile[0], 100, delta=1.5)
        self.assertAlmostEqual(c.mile[1], 200, delta=1.5)
        self.assertAlmostEqual(c.off_route[1], 4, delta=0.6)

    def test_sorted_by_mile(self):
        c = find_candidates(self.route, self.stations, corridor_miles=25)
        self.assertEqual(len(c.station_idx), 3)
        self.assertTrue(np.all(np.diff(c.mile) >= 0))

    def test_no_stations_nearby_gives_an_empty_result(self):
        far = make_stations([(100, 3.5, 200)])
        self.assertEqual(len(find_candidates(self.route, far, 5).station_idx), 0)


class MaxGap(unittest.TestCase):
    def test_includes_start_and_finish(self):
        self.assertEqual(max_gap(np.array([100.0, 300.0, 450.0]), 700.0), 250.0)

    def test_no_stations_is_the_whole_trip(self):
        self.assertEqual(max_gap(np.array([]), 400.0), 400.0)


class FeasibleCandidates(unittest.TestCase):
    def test_widens_the_corridor_to_close_a_gap(self):
        route = meridian_route(900)
        stations = make_stations([(450, 3.3, 8)])          # 8 miles off the road
        c = find_feasible_candidates(route, stations, max_range=500)
        self.assertEqual(c.corridor_miles, 10)             # 5 was not enough
        self.assertEqual(len(c.station_idx), 1)

    def test_raises_when_no_corridor_closes_the_gap(self):
        route = meridian_route(900)
        with self.assertRaises(NoFeasiblePlan) as ctx:
            find_feasible_candidates(route, make_stations([(450, 3.3, 200)]), max_range=500)
        self.assertIn("No feasible", str(ctx.exception))

    def test_short_trip_is_feasible_without_stations(self):
        route = meridian_route(300)
        c = find_feasible_candidates(route, make_stations([(100, 3.5, 200)]), max_range=500)
        self.assertEqual(len(c.station_idx), 0)


if __name__ == "__main__":
    unittest.main()
