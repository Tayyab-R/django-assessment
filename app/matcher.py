"""which stations are along the route, and at which mile marker?

Input : a Route and the Stations .
Output: Candidates, a flat 1D list sorted by mile marker. After this step the
        map is gone: the optimizer only sees (mile, price) pairs.
"""
from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from app.routing import Route
from app.stations import Stations, to_xyz

CORRIDOR_STEPS = (5, 10, 25)   # miles either side of the road; widen if there is a gap
ROUTE_SPACING_MILES = 1.0      # thin the route to about one point per mile


class NoFeasiblePlan(RuntimeError):
    """Even the widest corridor leaves a stretch longer than the vehicle's range."""


@dataclass(frozen=True)
class Candidates:
    station_idx: np.ndarray   # index into Stations arrays/records
    mile: np.ndarray          # miles from the start, along the route
    off_route: np.ndarray     # straight-line miles from the road
    price: np.ndarray         # $/gallon
    corridor_miles: float     # corridor width that produced this set


def thin_route(route: Route, spacing: float = ROUTE_SPACING_MILES) -> np.ndarray:
    """Indices of route points about `spacing` miles apart (always includes the last)."""
    n = len(route.cum_miles)
    marks = np.arange(0.0, route.total_miles, spacing)
    idx = np.clip(np.searchsorted(route.cum_miles, marks), 0, n - 1)
    return np.unique(np.append(idx, n - 1))


def find_candidates(route: Route, stations: Stations, corridor_miles: float) -> Candidates:
    """Stations within `corridor_miles` of the route, with their mile markers."""
    idx = thin_route(route)
    pts = to_xyz(route.lat[idx], route.lng[idx])

    # 1. Station tree (built once at startup), queried with the route's points.
    hits = stations.tree.query_ball_point(pts, r=corridor_miles)
    found = np.unique(np.fromiter((j for h in hits for j in h), dtype=np.int64))
    if found.size == 0:
        empty = np.array([])
        return Candidates(found, empty, empty, empty, corridor_miles)

    # 2. Small tree on the thinned route (~2,000 points) gives each candidate its
    #    nearest road point, and therefore its mile marker.
    dist, nearest = cKDTree(pts).query(stations.xyz[found])
    mile = route.cum_miles[idx[nearest]]

    order = np.lexsort((stations.price[found], mile))   # by mile, ties by price
    found, mile, dist = found[order], mile[order], dist[order]
    return Candidates(found, mile, dist, stations.price[found], corridor_miles)


def max_gap(mile: np.ndarray, total_miles: float) -> float:
    """Longest stretch with no fuel: start -> first stop -> ... -> last stop -> finish."""
    points = np.concatenate([[0.0], np.sort(mile), [total_miles]])
    return float(np.diff(points).max())


def find_feasible_candidates(route: Route, stations: Stations, max_range: float = 500.0) -> Candidates:
    """Try each corridor width until no gap exceeds the vehicle's range.

    Assumes the vehicle starts with a full tank, so the first stop must be within
    `max_range` of the start. Raises NoFeasiblePlan if nothing works.
    """
    gap = None
    for corridor in CORRIDOR_STEPS:
        cands = find_candidates(route, stations, corridor)
        gap = max_gap(cands.mile, route.total_miles)
        if gap <= max_range:
            return cands
    raise NoFeasiblePlan(
        f"No feasible fuel plan: even with a {CORRIDOR_STEPS[-1]}-mile corridor there is a "
        f"{gap:.0f}-mile stretch without fuel (range is {max_range:.0f} miles)."
    )