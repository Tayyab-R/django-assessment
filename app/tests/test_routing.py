import os
import unittest
from unittest import mock

import requests

from app import routing
from app.routing import RoutingError, build_route, get_route

COORDS = [[-87.6, 41.9], [-87.0, 41.0], [-86.0, 40.0]]           # [lng, lat]
START, END = (41.9, -87.6), (40.0, -86.0)                          # (lat, lng)


def ok_response(meters=300000.0, seconds=11000.0):
    resp = mock.Mock(status_code=200)
    resp.json.return_value = {"features": [{
        "geometry": {"coordinates": COORDS},
        "properties": {"summary": {"distance": meters, "duration": seconds}},
    }]}
    return resp


def status(code):
    return mock.Mock(status_code=code, text="nope")


class BuildRoute(unittest.TestCase):
    def test_mile_markers_start_at_zero_and_end_at_the_api_total(self):
        route = build_route(COORDS, 300000.0, 11000.0)
        self.assertEqual(route.cum_miles[0], 0.0)
        self.assertAlmostEqual(route.cum_miles[-1], 300000.0 / 1609.344)
        self.assertAlmostEqual(route.total_miles, route.cum_miles[-1])
        self.assertTrue(all(b > a for a, b in zip(route.cum_miles, route.cum_miles[1:])))

    def test_converts_seconds_to_hours(self):
        self.assertAlmostEqual(build_route(COORDS, 1000.0, 7200.0).duration_hours, 2.0)

    def test_rejects_a_geometry_with_fewer_than_two_points(self):
        with self.assertRaises(RoutingError):
            build_route([[-87.6, 41.9]], 1000.0)


class GetRoute(unittest.TestCase):
    def call(self, effects, **kw):
        with mock.patch("app.routing.requests.post", side_effect=effects) as post:
            try:
                result = get_route(START, END, api_key="key", **kw)
            except RoutingError as exc:
                result = exc
            return post, result

    def test_normal_request_makes_exactly_one_call(self):
        post, route = self.call([ok_response()])
        self.assertEqual(post.call_count, 1)
        self.assertAlmostEqual(route.total_miles, 300000.0 / 1609.344)

    def test_sends_lng_lat_order_and_unlimited_snap_radius(self):
        post, _ = self.call([ok_response()])
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["coordinates"], [[-87.6, 41.9], [-86.0, 40.0]])
        self.assertEqual(body["radiuses"], [-1, -1])
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "key")

    def test_retries_once_after_a_timeout(self):
        post, route = self.call([requests.Timeout("slow"), ok_response()])
        self.assertEqual(post.call_count, 2)
        self.assertGreater(route.total_miles, 0)

    def test_retries_once_after_a_503(self):
        post, route = self.call([status(503), ok_response()])
        self.assertEqual(post.call_count, 2)

    def test_gives_up_after_two_failures_with_a_clear_error(self):
        post, err = self.call([requests.Timeout("slow"), requests.Timeout("slow")])
        self.assertEqual(post.call_count, 2)
        self.assertIsInstance(err, RoutingError)
        self.assertIn("2 attempts", str(err))

    def test_client_errors_are_not_retried(self):
        post, err = self.call([status(403), ok_response()])
        self.assertEqual(post.call_count, 1)
        self.assertIsInstance(err, RoutingError)
        self.assertIn("403", str(err))

    def test_unexpected_response_shape_is_a_routing_error(self):
        bad = mock.Mock(status_code=200)
        bad.json.return_value = {}
        _, err = self.call([bad])
        self.assertIsInstance(err, RoutingError)

    def test_missing_api_key(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch("app.routing.requests.post") as post:
            with self.assertRaises(RoutingError):
                get_route(START, END)
            post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
