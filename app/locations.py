"""Module 3a: turn user input ("Chicago, IL" or "41.88,-87.62") into coordinates.

Uses places.json (built by build_stations), so no outside call is needed.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

from app.data_cleaning import normalize_city

# Continental US bounding box, same one used in the build_stations sanity check.
LAT_RANGE = (24.0, 50.0)
LNG_RANGE = (-125.0, -66.0)

_COORDS = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


class LocationError(ValueError):
    """The input could not be turned into a US location."""


@lru_cache(maxsize=2)
def load_places(path: Path | None = None) -> dict:
    """Read places.json once -> {(city_key, state): (lat, lng)}."""
    if path is None:
        from django.conf import settings

        path = Path(settings.BASE_DIR) / "app" / "data" / "places.json"
    with open(path) as f:
        rows = json.load(f)
    return {(r["city_key"], r["state"]): (r["lat"], r["lng"]) for r in rows}


def resolve_location(text: str, places: dict | None = None) -> tuple[float, float]:
    """Return (lat, lng) for 'City, ST' or 'lat,lng'. Raises LocationError."""
    if not isinstance(text, str) or not text.strip():
        raise LocationError("Location is required.")

    # Raw coordinates: "41.88,-87.62"
    m = _COORDS.match(text)
    if m:
        lat, lng = float(m.group(1)), float(m.group(2))
        if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LNG_RANGE[0] <= lng <= LNG_RANGE[1]):
            raise LocationError(f"Coordinates {lat},{lng} are outside the continental USA.")
        return lat, lng

    # "City, ST"
    if "," not in text:
        raise LocationError(f"Use the format 'City, ST' (e.g. 'Chicago, IL'): {text!r}")
    city, _, state = text.rpartition(",")
    state = state.strip().upper()
    if len(state) != 2:
        raise LocationError(f"State must be a 2-letter code (e.g. 'IL'): {text!r}")

    places = places if places is not None else load_places()
    found = places.get((normalize_city(city), state))
    if found is None:
        raise LocationError(f"Could not find {city.strip()!r}, {state} in the USA.")
    return found