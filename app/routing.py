"""Module 3b: the single outside API call (OpenRouteService directions)."""
from dataclasses import dataclass

import numpy as np
import requests
from django.conf import settings

ORS_URL = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
METERS_PER_MILE = 1609.344
EARTH_RADIUS_MILES = 3958.8


class RoutingError(RuntimeError):
    """The routing service failed or returned something unusable."""


@dataclass(frozen=True)
class Route:
    lat: np.ndarray          # (n,) degrees, along the road from start to finish
    lng: np.ndarray          # (n,)
    cum_miles: np.ndarray    # (n,) miles from the start; cum_miles[0] == 0
    total_miles: float
    duration_hours: float | None


def haversine_miles(lat1, lng1, lat2, lng2):
    """Great-circle distance in miles; works on numpy arrays."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = p2 - p1
    dlmb = np.radians(lng2) - np.radians(lng1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(a))


def build_route(coords_lng_lat, total_meters, duration_seconds=None) -> Route:
    """Turn the API's [[lng, lat], ...] list into a Route with mile markers."""
    arr = np.asarray(coords_lng_lat, dtype=float)
    if arr.ndim != 2 or arr.shape[0] < 2:
        raise RoutingError("Routing service returned no usable geometry.")
    lng, lat = arr[:, 0], arr[:, 1]

    steps = haversine_miles(lat[:-1], lng[:-1], lat[1:], lng[1:])
    cum = np.concatenate([[0.0], np.cumsum(steps)])

    # Trust the API's total distance; rescale our estimate to match it.
    total_miles = total_meters / METERS_PER_MILE
    if cum[-1] > 0:
        cum *= total_miles / cum[-1]
    hours = duration_seconds / 3600 if duration_seconds is not None else None
    return Route(lat, lng, cum, float(total_miles), hours)


def get_route(start: tuple[float, float], end: tuple[float, float], api_key: str | None = None) -> Route:
    """ONE call to the routing API. start/end are (lat, lng)."""

    api_key = api_key or settings.ORS_API_KEY
    if not api_key:
        raise RoutingError("ORS_API_KEY is not set.")

    body = {
        # ORS wants [lng, lat], the opposite of how we store points.
        "coordinates": [[start[1], start[0]], [end[1], end[0]]],
        # City centers are often not on a road. -1 = snap to the nearest road
        # at any distance, instead of failing beyond the default 350 m.
        "radiuses": [-1, -1],
    }
    try:
        resp = requests.post(
            ORS_URL,
            json=body,
            headers={"Authorization": api_key, "Content-Type": "application/json"},
            timeout=20,
        )
    except requests.RequestException as exc:
        raise RoutingError(f"Could not reach the routing service: {exc}") from exc

    if resp.status_code != 200:
        raise RoutingError(f"Routing service returned {resp.status_code}: {resp.text[:200]}")

    try:
        feature = resp.json()["features"][0]
        coords = feature["geometry"]["coordinates"]
        summary = feature["properties"]["summary"]
        return build_route(coords, summary["distance"], summary.get("duration"))
    except (KeyError, IndexError, ValueError) as exc:
        raise RoutingError("Unexpected response format from routing service.") from exc