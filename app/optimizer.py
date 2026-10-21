"""choose where to stop and how much fuel to buy.

Input : Candidates (Module 4), a flat list of (mile, price) sorted by mile.
Output: a FuelPlan with the stops, gallons, and total cost.

The rule, applied at every station:
  * if a CHEAPER station is within one full tank, buy only enough to reach the
    nearest such station and let it supply the rest;
  * otherwise this is the best price around: fill the tank, then move on.
The finish line is treated as a station with price 0, so "buy just enough to
finish" falls out of the same rule.
"""
from dataclasses import dataclass

import numpy as np

from app.matcher import Candidates, NoFeasiblePlan

EPS = 1e-9


@dataclass(frozen=True)
class Stop:
    station_idx: int   # index into Stations.records
    mile: float
    price: float       # $/gallon
    gallons: float
    cost: float        # dollars


@dataclass(frozen=True)
class FuelPlan:
    stops: list
    total_cost: float
    gallons_purchased: float
    trip_gallons: float   # total_miles / mpg: all fuel the trip burns


def plan_fuel(
    cands: Candidates,
    total_miles: float,
    max_range: float = 500.0,
    mpg: float = 10.0,
    start_fuel_miles: float | None = None,
) -> FuelPlan:
    """Cheapest set of stops. The vehicle starts with `start_fuel_miles` of fuel
    (default: a full tank, not billed); fuel can only be bought at stations."""
    fuel = max_range if start_fuel_miles is None else start_fuel_miles

    # One entry per mile marker: the cheapest station there (stations that share
    # a city share a mile marker, so only the cheapest of them matters).
    order = np.lexsort((cands.price, cands.mile))
    mile, price, sid = cands.mile[order], cands.price[order], cands.station_idx[order]
    _, first = np.unique(mile, return_index=True)
    mile, price, sid = mile[first], price[first], sid[first]

    # Node 0 = the start (price inf: nothing can be bought there).
    # Last node = the finish (price 0: always "cheaper", so we just buy enough to reach it).
    miles = np.concatenate([[0.0], mile, [total_miles]])
    prices = np.concatenate([[np.inf], price, [0.0]])
    sids = np.concatenate([[-1], sid, [-1]])

    stops = []
    c, last = 0, len(miles) - 1
    while c < last:
        # Nearest strictly-cheaper node within one full tank.
        target = None
        j = c + 1
        while j <= last and miles[j] - miles[c] <= max_range + EPS:
            if prices[j] < prices[c]:
                target = j
                break
            j += 1

        if target is not None:
            dist = miles[target] - miles[c]
            buy = max(0.0, dist - fuel)            # just enough to get there
        else:
            target = c + 1                          # nothing cheaper: fill up
            dist = miles[target] - miles[c]
            if dist > max_range + EPS:
                raise NoFeasiblePlan(f"{dist:.0f}-mile gap after mile {miles[c]:.0f} exceeds the range.")
            buy = max_range - fuel

        if buy > EPS:
            if c == 0:
                raise NoFeasiblePlan("The starting fuel does not reach the first station.")
            gallons = float(buy) / mpg
            stops.append(Stop(int(sids[c]), float(miles[c]), float(prices[c]), gallons, float(gallons * prices[c])))

        fuel = fuel + buy - dist
        c = target

    return FuelPlan(
        stops=stops,
        total_cost=float(sum(s.cost for s in stops)),
        gallons_purchased=float(sum(s.gallons for s in stops)),
        trip_gallons=total_miles / mpg,
    )