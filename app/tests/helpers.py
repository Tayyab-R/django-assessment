"""Small builders so tests can create routes, stations and candidates in one line."""
import math

import numpy as np
from scipy.spatial import cKDTree

from app.matcher import Candidates
from app.routing import METERS_PER_MILE, build_route
from app.stations import Stations, to_xyz

MILES_PER_DEG_LAT = 2 * math.pi * 3958.8 / 360   # ~69.09
START_LAT = 30.0
LNG = -90.0


def meridian_route(total_miles: float, n: int = 3000):
    """A straight north-bound route, so mile N sits at a known latitude."""
    lat = np.linspace(START_LAT, START_LAT + total_miles / MILES_PER_DEG_LAT, n)
    coords = np.column_stack([np.full(n, LNG), lat])
    return build_route(coords, total_miles * METERS_PER_MILE, total_miles / 60 * 3600)


def point_at(mile: float, off_miles: float = 0.0):
    """(lat, lng) of a point `mile` miles along the route, `off_miles` east of it."""
    lat = START_LAT + mile / MILES_PER_DEG_LAT
    dlng = off_miles / (MILES_PER_DEG_LAT * math.cos(math.radians(lat)))
    return lat, LNG + dlng


def make_stations(spec) -> Stations:
    """spec: list of (mile, price) or (mile, price, off_route_miles)."""
    lats, lngs, prices, records = [], [], [], []
    for i, item in enumerate(spec):
        mile, price = item[0], item[1]
        off = item[2] if len(item) > 2 else 0.0
        lat, lng = point_at(mile, off)
        lats.append(lat); lngs.append(lng); prices.append(price)
        records.append({"stop_id": i, "name": f"STOP {i}", "city": "Town", "state": "XX",
                        "price": price, "lat": lat, "lng": lng})
    lat_a, lng_a, price_a = np.array(lats), np.array(lngs), np.array(prices, dtype=float)
    xyz = to_xyz(lat_a, lng_a)
    return Stations(records, lat_a, lng_a, price_a, xyz, cKDTree(xyz))


def candidates(pairs) -> Candidates:
    """Candidates straight from (mile, price) pairs, for optimizer tests."""
    pairs = sorted(pairs)
    mile = np.array([p[0] for p in pairs], dtype=float)
    price = np.array([p[1] for p in pairs], dtype=float)
    n = len(pairs)
    return Candidates(np.arange(n), mile, np.zeros(n), price, 5)
