# Fuel Route API

A Django API that takes a start and a finish location in the USA and returns:

- the driving route (GeoJSON) and a Leaflet map of it,
- the cost-optimal fuel stops along the route, with how much to buy at each,
- the total money spent on fuel.

The vehicle has a 500-mile range and gets 10 miles per gallon. Fuel prices come
from `fuel-prices-for-be-assessment.csv`. Routing uses the free
[OpenRouteService](https://openrouteservice.org) API, called **once** per new trip.

## How it works

```
POST /api/route/  {"start": "Chicago, IL", "finish": "Los Angeles, CA"}
        |
        v
 1. resolve both places offline       (places.json, no API call)
 2. ONE call to OpenRouteService      (route geometry + distance + duration)
 3. find stations along the route     (KD-tree on stations, 5/10/25-mile corridor)
 4. choose the cheapest stops         (greedy rule, below)
 5. return JSON + a map link
```

**Stop selection.** At each station, look at everything reachable on one full tank.
If a *cheaper* station is within range, buy only enough to reach the nearest one.
Otherwise this is the best price around, so fill the tank (or buy just enough to
finish, since the finish counts as a free station). The test suite checks this rule
against an exact dynamic-programming solver on random trips.

**Speed.** Everything after the routing call takes a few milliseconds (matching
about 3 ms, optimizing under 1 ms). A new trip costs about 2-3 seconds in total, almost
all of it the single OpenRouteService call. Repeating a trip is served from the Django
cache with no routing call. Station data is loaded once into numpy arrays with a
prebuilt KD-tree, so a request never reads from disk.

## Setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/). Dependencies (Django 6.1,
numpy, scipy, pandas, requests) are declared in `pyproject.toml` and pinned in `uv.lock`.

```bash
uv sync                                          # creates .venv and installs everything
export ORS_API_KEY="your-openrouteservice-key"   # free key from openrouteservice.org
uv run python manage.py runserver
```

Run the commands from the folder that contains `manage.py` and `pyproject.toml`.

`stations.json` and `places.json` are committed under `app/data/`, so the API runs
without any data preparation. To regenerate them (optional):

1. Download the GeoNames US postal-code file (`download.geonames.org/export/zip/US.zip`),
   unzip it, and place `US.txt` in `app/data/`.
2. Run `uv run python manage.py build_stations`.

The command drops the Canadian rows, keeps the lowest price per truck stop,
geocodes each stop by city and state, sanity-checks the coordinates, and writes both files.

## API

### `POST /api/route/`

```json
{"start": "Chicago, IL", "finish": "Los Angeles, CA"}
```

Locations are `"City, ST"` (two-letter state) or raw `"lat,lng"` inside the continental US.

Response (abridged, from a real Chicago to Los Angeles run):

```json
{
  "total_miles": 2017.8,
  "duration_hours": 31.69,
  "fuel": {
    "stops": [
      {"name": "Henderson Fuel Mart", "city": "Henderson", "state": "NE",
       "mile": 574.2, "price_per_gallon": 2.899, "gallons": 50.0, "cost": 144.95,
       "lat": 40.7814, "lng": -97.7979}
    ],
    "total_cost": 466.58,
    "gallons_purchased": 151.78,
    "trip_gallons": 201.78
  },
  "route": {"type": "LineString", "coordinates": [[-87.6759, 41.85421], "..."]},
  "assumptions": {"max_range_miles": 500.0, "miles_per_gallon": 10.0, "...": "..."},
  "timing_ms": {"routing_api": 2891.7, "matching": 3.2, "optimizing": 0.3, "total": 2895.2},
  "map_url": "http://127.0.0.1:8000/api/map/9a0c250df5cc90be/",
  "cached": false
}
```

(That run had 11 stops.)

| Status | Meaning |
|---|---|
| 400 | Invalid JSON, missing field, unknown or non-US place, or start equals finish |
| 422 | No feasible fuel plan (a stretch longer than 500 miles with no station, even in a 25-mile corridor) |
| 502 | The routing service failed |

### `GET /api/map/<id>/`

Open the `map_url` from the response in a browser: the route, the start and finish,
the fuel stops and a summary panel, on OpenStreetMap tiles.

The map page needs `SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"`
(set in `settings.py`) because OpenStreetMap's tile servers require a Referer header.

## Assumptions

- **Starting tank is full and not billed.** `total_cost` is the money spent on fuel
  bought at the stops. A trip under 500 miles therefore needs no stops and costs $0.
  `gallons_purchased + 50` equals `trip_gallons`.
- **One price per truck stop.** The CSV has several prices for some stops and no
  timestamps, so the lowest is used.
- **Stations are placed at city level.** The CSV has no coordinates (its addresses are
  highway exits), so each stop is geocoded by city and state with the offline GeoNames
  dataset. Positions are approximate to a few miles.
- **Stations within a corridor of the route** (5 miles, widened to 10 and 25 if there
  would otherwise be a gap over 500 miles) count as on the route. The detour is not
  priced.
- **Mile markers** come from the routing API's total distance, with a resolution of
  about one mile.
- Canadian rows in the CSV are ignored.

## Known limitations

- Because the plan is cheapest-possible, it can include very small purchases (for
  example 1.4 gallons). A minimum purchase size would be a natural refinement.
- Station positions are approximate (city level, see above).
- The cache is Django's cache: with the default in-memory backend, cached trips and
  map links are lost when the server restarts. Use a file-based or shared cache in
  production.
- OpenRouteService's free plan allows 2,000 directions requests per day, and the
  routing call is retried once on a timeout or a 5xx response.
- Only the continental USA is supported.

## Tests

```bash
uv run python manage.py test app
```

52 tests cover the optimizer (including a comparison with an exact solver), the
matcher, location parsing, the routing client (mocked, including retries), the whole
pipeline and the HTTP endpoints. No test calls the real routing service.

## Project layout

```
app/
  cleaning.py          CSV cleaning and city-name normalization
  stations.py          loads stations.json into numpy arrays + KD-tree
  locations.py         "City, ST" / "lat,lng" -> coordinates (offline)
  routing.py           the single OpenRouteService call (with one retry)
  matcher.py           stations along the route, mile markers, gap check
  optimizer.py         cheapest fuel stops
  pipeline.py          the whole trip-planning flow as one function
  views.py, urls.py    POST /api/route/ and GET /api/map/<id>/
  templates/app/map.html
  management/commands/build_stations.py
  data/                fuel CSV, stations.json, places.json
  tests/
```