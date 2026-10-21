import unittest

from app.data_cleaning import normalize_city
from app.locations import LocationError, resolve_location

PLACES = {
    (normalize_city("Chicago"), "IL"): (41.85, -87.68),
    (normalize_city("Winston-Salem"), "NC"): (36.1, -80.2),
    (normalize_city("Saint Louis"), "MO"): (38.63, -90.2),
}


class ResolveByName(unittest.TestCase):
    def test_city_and_state(self):
        self.assertEqual(resolve_location("Chicago, IL", PLACES), (41.85, -87.68))

    def test_ignores_case_and_spacing(self):
        self.assertEqual(resolve_location("  chicago ,il ", PLACES), (41.85, -87.68))

    def test_spelling_variants_match(self):
        self.assertEqual(resolve_location("Winston Salem, NC", PLACES), (36.1, -80.2))
        self.assertEqual(resolve_location("St. Louis, MO", PLACES), (38.63, -90.2))


class ResolveCoordinates(unittest.TestCase):
    def test_lat_lng_pair(self):
        self.assertEqual(resolve_location("41.88,-87.62", PLACES), (41.88, -87.62))

    def test_outside_the_us_is_rejected(self):
        with self.assertRaises(LocationError):
            resolve_location("10,10", PLACES)


class BadInput(unittest.TestCase):
    def test_each_bad_input_raises_a_location_error(self):
        for bad in ["", "   ", None, "Chicago", "Chicago IL", "Chicago, Illinois", "Atlantis, IL"]:
            with self.subTest(bad=bad), self.assertRaises(LocationError):
                resolve_location(bad, PLACES)


if __name__ == "__main__":
    unittest.main()
