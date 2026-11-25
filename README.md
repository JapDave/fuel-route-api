# Fuel Route Planner

A Django 6.1.3 and Django REST Framework API for planning US road trips with fuel stops from a supplied OPIS retail-price CSV. It returns the route and fuel stops as GeoJSON, leg distances, gallons to buy, and estimated USD fuel costs.

## Run locally

Python 3.12 or newer is required. On macOS or Linux, open Terminal in this folder and run:

```sh
cp .env.example .env
# Add your Geoapify key to .env, then:
./run-local.sh
```

The command creates a virtual environment on first run, installs dependencies, and starts the API server at `http://127.0.0.1:8000`. If your Mac's default Python is older, run `PYTHON_BIN=python3.12 ./run-local.sh` with an installed Python 3.12 (or newer executable). On Windows, run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Create a free server-side Geoapify key and set `GEOAPIFY_API_KEY` in `.env`. The key is required and `.env` is excluded from Git. Start and finish may be US cities or street addresses.

## API

Send `POST /api/v1/route/` with `Content-Type: application/json`.

```sh
curl http://127.0.0.1:8000/api/v1/route/ \
  -H 'Content-Type: application/json' \
  --data '{"start":"Dallas, TX","finish":"Denver, CO"}'
```

Import [Fuel_Route.postman_collection.json](Fuel_Route.postman_collection.json) into Postman for a one-stop route, a multi-stop cross-country route, and a short route. The API also accepts `starting_price_per_gallon` as an optional USD price to value the fuel already in the tank.

| Response field | Meaning |
| --- | --- |
| `map` | GeoJSON FeatureCollection containing the road route, start and finish points, fuel stops, and straight-line links to their route projections. Coordinate order is longitude, latitude. |
| `summary.leg_distances_miles` | Estimated driving distance between consecutive stops, including station access. Each leg is at most 500 miles under the distance model. |
| `summary.fuel_purchased_en_route_usd` | Estimated cash paid for fuel at the recommended stops. |
| `summary.estimated_total_fuel_cost_usd` | En-route purchases plus the estimated value of fuel used from the starting tank. A caller-supplied starting price takes precedence over the catalog median. |
| `fuel_stops` | Outlet name, address, map location precision, estimated gallons to buy, arrival and departure tank levels, and price. USD fields are strings to preserve decimal precision. |

Bad inputs return HTTP 400. Unknown places, disconnected endpoints, or a gap too large to cover with the catalog return HTTP 422 with an error code. Missing or rejected credentials and exhausted quota return 503. Geoapify connectivity, response, and timeout failures return 502 or 504.

## Import price data

The supplied CSV lists outlet IDs, highway or street addresses, cities, states, and retail prices, with no latitude or longitude. The import uses the [2025 Census national Places Gazetteer](https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2025_Gazetteer/2025_Gaz_place_national.zip) and optionally [GeoNames US.zip](https://download.geonames.org/export/dump/US.zip) for additional towns. Census and GeoNames files are downloaded once and are read locally during import.

```sh
mkdir -p data
curl -fL https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2025_Gazetteer/2025_Gaz_place_national.zip -o data/gazetteer.zip
curl -fL https://download.geonames.org/export/dump/US.zip -o data/geonames.zip
./.venv/bin/python manage.py import_fuel_prices data/fuel-prices-for-be-assessment.csv \
  --gazetteer data/gazetteer.zip --geonames data/geonames.zip
```

The import deduplicates rows by OPIS truck-stop ID, using the lowest supplied price when rows differ because the sheet contains no timestamps. The unmatched rows report lists outlets skipped for missing or ambiguous city matches. Add verified station coordinates using `--overrides path/to/coordinates.csv` with the headers `id,longitude,latitude`. An override replaces the outlet's locality point and changes its response precision from `city_centroid` to `station`.

The source price sheet does not contain coordinates. After the initial import, use Geoapify's batch geocoder once to replace approximate city points with validated address results:

```sh
./.venv/bin/python manage.py geocode_fuel_stations
```

The command submits at most 1,000 addresses per batch, saves the catalog after every completed batch, and can be resumed. Results must be in the expected US state, have at least 0.60 confidence, and resolve to an amenity, building, or street. Rejected results are written to `data/stations-geocoding-unmatched.csv` for review. Use `--max-records` when you need to stay within a daily API quota.

The outlet addresses and prices are from the supplied snapshot. City-center markers and their access distances are approximate. The project uses passenger-car routing because the brief supplies fuel economy and range without vehicle dimensions or truck restrictions.

## Routing and cost model

- A cold request uses two parallel, US-filtered Geoapify geocodes and one Geoapify route call. Successful geocodes are cached for 24 hours and routes for 15 minutes. Candidate stations never trigger routing API calls.
- An in-memory geographic grid finds stations within eight straight-line miles of the road. The planner estimates road progress from the route polyline and estimates one-way station access at 1.3 times the point-to-route distance. Both directions of access are included in the range and fuel-cost model.
- The vehicle starts with 50 gallons and burns one gallon per 10 miles. The optimizer finds the lowest purchase cost over the candidate stations in route order. Its graph uses empty-arrival and full-departure states to model partial top-ups, cheaper stations farther ahead, and the 500-mile range. For equal cost it prefers fewer stops.
- Prices are a supplied snapshot. The reported optimum applies to the selected route, available catalog stations, and estimated access legs. Map linework represents the base road route plus approximate station access links. Route duration excludes time spent reaching or stopping at stations.

Routing and geocoding are powered by [Geoapify](https://www.geoapify.com/) with data © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright). Supplemental place data © [GeoNames](https://www.geonames.org/) under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

## Tests

```sh
./.venv/bin/python manage.py test
```

Tests replace Geoapify with deterministic fixtures and do not spend API credits. Postman can display the live JSON response, GeoJSON route geometry, fuel stops, and elapsed time. For a code walkthrough, open `planner/providers.py`, then `planner/geometry.py` and `planner/optimizer.py`.
