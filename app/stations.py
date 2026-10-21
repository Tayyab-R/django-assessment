"""load stations.json once and keep it in memory as numpy arrays."""
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

EARTH_RADIUS_MILES = 3958.8


def to_xyz(lat, lng):
    """Convert lat/lng (degrees) to 3D points on a sphere, in miles.

    Straight-line distance between two such points is close to the real
    distance, so it can be used with a KD-tree. Accepts scalars or arrays;
    returns an array of shape (..., 3).
    """
    lat_r = np.radians(lat)
    lng_r = np.radians(lng)
    x = EARTH_RADIUS_MILES * np.cos(lat_r) * np.cos(lng_r)
    y = EARTH_RADIUS_MILES * np.cos(lat_r) * np.sin(lng_r)
    z = EARTH_RADIUS_MILES * np.sin(lat_r)
    return np.stack([x, y, z], axis=-1)


@dataclass(frozen=True)
class Stations:
    records: list      # original dicts, used to build the API response
    lat: np.ndarray
    lng: np.ndarray
    price: np.ndarray
    xyz: np.ndarray    # shape (n, 3), miles
    tree: cKDTree      # built once; answers 'which stations are near this point?'


def _default_path() -> Path:
    from django.conf import settings

    return Path(settings.BASE_DIR) / "app" / "data" / "stations.json"


@lru_cache(maxsize=4)
def load_stations(path: Path | None = None) -> Stations:
    """Read stations.json. Cached, so the file is only read once per process."""
    path = Path(path) if path else _default_path()
    with open(path) as f:
        records = json.load(f)

    lat = np.array([r["lat"] for r in records], dtype=float)
    lng = np.array([r["lng"] for r in records], dtype=float)
    price = np.array([r["price"] for r in records], dtype=float)
    xyz = to_xyz(lat, lng)
    return Stations(records, lat, lng, price, xyz, cKDTree(xyz))