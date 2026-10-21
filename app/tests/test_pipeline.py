import json
import unittest
from unittest import mock

from app import pipeline
from app.data_cleaning import normalize_city
from app.locations import LocationError
from app.matcher import NoFeasiblePlan
from app.tests.helpers import MILES_PER_DEG_LAT, START_LAT, LNG, make_stations, meridian_route

TOTAL = 1000
PLACES = {
    (normalize_city("Startville"), "TX"): (START_LAT, LNG),
    (normalize_city("Endton"), "TX"): (START_LAT + TOTAL / MILES_PER_DEG_LAT, LNG),
}
# a station every 100 miles, with prices that wobble
STATIONS = make_stations([(m, p, 1.0) for m, p in
                          zip(range(50, 1000, 100), [3.6, 3.2, 3.9, 3.1, 3.5, 3.0, 3.8, 3.3, 3.4, 3.7])])


class PlanTrip(unittest.TestCase):
    def run_pipeline(self, stations=STATIONS, start="Startville, TX", finish="Endton, TX"):
        calls = []

        def fake_route(a, b):
            calls.append((a, b))
            return meridian_route(TOTAL)

        with mock.patch("app.locations.load_places", return_value=PLACES), \
                mock.patch("app.pipeline.load_stations", return_value=stations):
            result = pipeline.plan_trip(start, finish, route_fn=fake_route)
        return result, calls

    def test_makes_one_routing_call(self):
        _, calls = self.run_pipeline()
        self.assertEqual(len(calls), 1)

    def test_response_has_the_expected_parts(self):
        out, _ = self.run_pipeline()
        for key in ("start", "finish", "total_miles", "duration_hours", "fuel", "route",
                    "assumptions", "timing_ms", "candidate_stations"):
            self.assertIn(key, out)
        self.assertAlmostEqual(out["total_miles"], TOTAL, delta=0.1)
        self.assertEqual(out["route"]["type"], "LineString")
        self.assertEqual(out["route"]["coordinates"][0], [LNG, START_LAT])
        self.assertEqual(out["assumptions"]["max_range_miles"], 500.0)
        self.assertEqual(out["assumptions"]["miles_per_gallon"], 10.0)

    def test_stops_are_ordered_and_add_up(self):
        out, _ = self.run_pipeline()
        fuel = out["fuel"]
        miles = [s["mile"] for s in fuel["stops"]]
        self.assertTrue(fuel["stops"])
        self.assertEqual(miles, sorted(miles))
        self.assertTrue(all(0 <= m <= TOTAL for m in miles))
        # fuel bought + the free 50-gallon starting tank == fuel the trip burns
        self.assertAlmostEqual(fuel["gallons_purchased"] + 50, fuel["trip_gallons"], delta=0.05)
        self.assertAlmostEqual(fuel["total_cost"], sum(s["cost"] for s in fuel["stops"]), delta=0.1)

    def test_result_is_json_serializable(self):
        out, _ = self.run_pipeline()
        json.dumps(out)

    def test_same_start_and_finish_is_rejected(self):
        with self.assertRaises(LocationError):
            self.run_pipeline(start="Startville, TX", finish="Startville, TX")

    def test_unknown_city_is_rejected(self):
        with self.assertRaises(LocationError):
            self.run_pipeline(finish="Atlantis, TX")

    def test_infeasible_trip_raises(self):
        with self.assertRaises(NoFeasiblePlan):
            self.run_pipeline(stations=make_stations([(500, 3.0, 100)]))


if __name__ == "__main__":
    unittest.main()
