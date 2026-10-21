"""HTTP-level tests. These need Django, so run them with `python manage.py test`."""
import json
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from app.locations import LocationError
from app.matcher import NoFeasiblePlan
from app.routing import RoutingError

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
PAYLOAD = {"total_miles": 100.0, "timing_ms": {"total": 5.0}}
GOOD = {"start": "Chicago, IL", "finish": "Los Angeles, CA"}


@override_settings(CACHES=LOCMEM)
class RouteEndpoint(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse("plan-route")

    def post(self, body, raw=False):
        data = body if raw else json.dumps(body)
        return self.client.post(self.url, data=data, content_type="application/json")

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_invalid_json_is_a_400(self):
        self.assertEqual(self.post("not json", raw=True).status_code, 400)

    def test_missing_fields_are_a_400(self):
        self.assertEqual(self.post({"start": "Chicago, IL"}).status_code, 400)
        self.assertEqual(self.post([]).status_code, 400)

    def test_success_returns_the_plan_and_a_map_link(self):
        with mock.patch("app.views.plan_trip", return_value=dict(PAYLOAD)):
            resp = self.post(GOOD)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["total_miles"], 100.0)
        self.assertFalse(body["cached"])
        self.assertIn("/map/", body["map_url"])

    def test_repeat_request_is_served_from_cache(self):
        with mock.patch("app.views.plan_trip", return_value=dict(PAYLOAD)) as plan:
            first = self.post(GOOD).json()
            again = self.post({"start": " chicago,  il", "finish": "los angeles, ca"}).json()
        self.assertEqual(plan.call_count, 1)
        self.assertTrue(again["cached"])
        self.assertEqual(first["map_url"], again["map_url"])
        self.assertIn("served from cache", again["timing_ms"]["note"])

    def test_errors_map_to_http_statuses(self):
        cases = [(LocationError("bad place"), 400), (NoFeasiblePlan("no fuel"), 422),
                 (RoutingError("down"), 502)]
        for exc, code in cases:
            with self.subTest(exc=type(exc).__name__), \
                    mock.patch("app.views.plan_trip", side_effect=exc):
                resp = self.post(GOOD)
                self.assertEqual(resp.status_code, code)
                self.assertIn("error", resp.json())

    def test_failures_are_not_cached(self):
        with mock.patch("app.views.plan_trip", side_effect=RoutingError("down")):
            self.assertEqual(self.post(GOOD).status_code, 502)
        with mock.patch("app.views.plan_trip", return_value=dict(PAYLOAD)):
            self.assertEqual(self.post(GOOD).status_code, 200)


@override_settings(CACHES=LOCMEM)
class MapEndpoint(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_map_page_renders_for_a_planned_trip(self):
        with mock.patch("app.views.plan_trip", return_value=dict(PAYLOAD)):
            body = self.client.post(reverse("plan-route"), data=json.dumps(GOOD),
                                    content_type="application/json").json()
        resp = self.client.get(body["map_url"])
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "app/map.html")

    def test_unknown_map_id_is_a_404(self):
        self.assertEqual(self.client.get(reverse("route-map", args=["nope"])).status_code, 404)

    def test_map_page_is_get_only(self):
        self.assertEqual(self.client.post(reverse("route-map", args=["x"])).status_code, 405)
