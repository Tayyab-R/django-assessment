"""Module 6b: the HTTP layer as class-based views. Thin on purpose: parse, call the pipeline, reply."""
import hashlib
import json
from time import perf_counter

from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from app.locations import LocationError
from app.matcher import NoFeasiblePlan
from app.pipeline import plan_trip
from app.routing import RoutingError

CACHE_SECONDS = 60 * 60


def _error(message: str, status: int) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


def _norm(text) -> str:
    return " ".join(str(text).lower().split())


# csrf_exempt: a JSON API called from Postman/scripts, there is no browser session.
@method_decorator(csrf_exempt, name="dispatch")
class PlanRouteView(View):
    """POST {"start": "...", "finish": "..."} -> fuel plan, route and map link."""

    http_method_names = ["post", "options"]   # anything else gets 405 automatically

    def post(self, request):
        t0 = perf_counter()
        try:
            body = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return _error("Request body must be valid JSON.", 400)
        if not isinstance(body, dict):
            return _error('Send a JSON object: {"start": "...", "finish": "..."}.', 400)

        start, finish = body.get("start"), body.get("finish")
        if not start or not finish:
            return _error('Both "start" and "finish" are required.', 400)

        key = hashlib.sha1(f"{_norm(start)}|{_norm(finish)}".encode()).hexdigest()[:16]
        payload = cache.get(f"trip:{key}")
        cached = payload is not None

        if payload is None:
            try:
                payload = plan_trip(str(start), str(finish))
            except LocationError as exc:
                return _error(str(exc), 400)
            except NoFeasiblePlan as exc:
                return _error(str(exc), 422)
            except RoutingError as exc:
                return _error(str(exc), 502)
            cache.set(f"trip:{key}", payload, CACHE_SECONDS)

        # The map page reads the same payload, so it costs no extra routing call.
        cache.set(f"map:{key}", payload, CACHE_SECONDS)
        map_url = request.build_absolute_uri(reverse("route-map", args=[key]))
        response = {**payload, "map_url": map_url, "cached": cached}
        if cached:
            # The stored timings belong to the first request; report this one's.
            response["timing_ms"] = {
                "total": round((perf_counter() - t0) * 1000, 1),
                "note": "served from cache, no routing API call",
            }
        return JsonResponse(response)


class RouteMapView(View):
    """GET /api/map/<id>/ -> Leaflet page for a trip planned earlier."""

    http_method_names = ["get", "head", "options"]

    def get(self, request, map_id):
        payload = cache.get(f"map:{map_id}")
        if payload is None:
            return _error("This map has expired. POST to /api/route/ again.", 404)
        return render(request, "app/map.html", {"data": payload})