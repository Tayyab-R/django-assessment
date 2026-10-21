"""the whole trip-planning pipeline as one plain function.

No HTTP in here, so it can be tested without Django and reused by any view.
"""
from time import perf_counter

from app.locations import LocationError, resolve_location
from app.matcher import find_feasible_candidates, thin_route
from app.optimizer import plan_fuel
from app.routing import get_route, haversine_miles
from app.stations import load_stations

MAX_RANGE_MILES = 500.0
MPG = 10.0


def _ms(t0: float, t1: float) -> float:
    return round((t1 - t0) * 1000, 1)


def plan_trip(start_text: str, finish_text: str, route_fn=get_route) -> dict:
    """Start/finish text in, JSON-ready dict out.

    Raises LocationError, RoutingError or NoFeasiblePlan (the view maps them to
    HTTP errors). `route_fn` is injectable so tests don't call the real API.
    """
    t0 = perf_counter()
    start = resolve_location(start_text)
    finish = resolve_location(finish_text)
    if haversine_miles(start[0], start[1], finish[0], finish[1]) < 1.0:
        raise LocationError("Start and finish are the same place.")
    stations = load_stations()
    t1 = perf_counter()

    route = route_fn(start, finish)              # the ONE outside API call
    t2 = perf_counter()

    cands = find_feasible_candidates(route, stations, MAX_RANGE_MILES)
    t3 = perf_counter()

    plan = plan_fuel(cands, route.total_miles, MAX_RANGE_MILES, MPG)
    t4 = perf_counter()

    stops = []
    for s in plan.stops:
        rec = stations.records[s.station_idx]
        stops.append({
            "stop_id": int(rec["stop_id"]),
            "name": rec["name"],
            "city": rec["city"],
            "state": rec["state"],
            "lat": float(rec["lat"]),
            "lng": float(rec["lng"]),
            "mile": round(s.mile, 1),
            "price_per_gallon": round(s.price, 4),
            "gallons": round(s.gallons, 2),
            "cost": round(s.cost, 2),
        })

    # Draw the route with about one point per mile (14k points -> ~2k).
    idx = thin_route(route)
    line = [[round(float(route.lng[i]), 5), round(float(route.lat[i]), 5)] for i in idx]

    return {
        "start": {"input": start_text, "lat": start[0], "lng": start[1]},
        "finish": {"input": finish_text, "lat": finish[0], "lng": finish[1]},
        "total_miles": round(route.total_miles, 1),
        "duration_hours": round(route.duration_hours, 2) if route.duration_hours else None,
        "fuel": {
            "stops": stops,
            "total_cost": round(plan.total_cost, 2),
            "gallons_purchased": round(plan.gallons_purchased, 2),
            "trip_gallons": round(plan.trip_gallons, 2),
        },
        "route": {"type": "LineString", "coordinates": line},
        "assumptions": {
            "max_range_miles": MAX_RANGE_MILES,
            "miles_per_gallon": MPG,
            "starting_fuel": "full tank, not billed; total_cost is fuel bought at the stops",
            "station_positions": "city-level (approximate), matched within a "
                                 f"{cands.corridor_miles:g}-mile corridor of the route",
        },
        "candidate_stations": int(len(cands.station_idx)),
        "timing_ms": {
            "lookup": _ms(t0, t1),
            "routing_api": _ms(t1, t2),
            "matching": _ms(t2, t3),
            "optimizing": _ms(t3, t4),
            "total": _ms(t0, t4),
        },
    }