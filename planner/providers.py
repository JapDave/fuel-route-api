"""Geoapify geocoding and routing integration."""

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from math import isfinite
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache

from .domain import Location, METERS_PER_MILE, PlanningError, Route

BASE_URL = "https://api.geoapify.com/v1/"
GEOCODE_TTL = 60 * 60 * 24
ROUTE_TTL = 60 * 15


def _cache_key(prefix, value):
    digest = sha256(repr(value).encode()).hexdigest()
    return f"{prefix}:{digest}"


def _api_key():
    key = settings.GEOAPIFY_API_KEY.strip()
    if not key:
        raise PlanningError(
            "geoapify_not_configured",
            "Set GEOAPIFY_API_KEY before requesting a route.",
            503,
        )
    return key


def geoapify_request(path, params=None, *, method="GET", body=None, routing=False):
    """Return ``(HTTP status, decoded JSON)`` for a Geoapify request."""
    query = urlencode({**(params or {}), "apiKey": _api_key()})
    payload = None if body is None else json.dumps(body).encode()
    request = Request(
        f"{BASE_URL}{path}?{query}",
        data=payload,
        method=method,
        headers={
            "User-Agent": "FuelRouteAssignment/1.0",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=10) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise PlanningError(
                "geoapify_authentication_failed",
                "Geoapify rejected the configured API key.",
                503,
            ) from None
        if exc.code == 429:
            raise PlanningError(
                "geoapify_rate_limited",
                "Geoapify's request limit has been reached. Try again later.",
                503,
            ) from None
        if routing and exc.code in (400, 404, 422):
            raise PlanningError(
                "no_drivable_route",
                "Geoapify could not find a drivable route between these locations.",
            ) from None
        raise PlanningError(
            "geoapify_unavailable",
            "Geoapify could not complete the request.",
            502,
        ) from None
    except TimeoutError:
        raise PlanningError(
            "geoapify_timeout", "Geoapify did not respond in time.", 504
        ) from None
    except URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise PlanningError(
                "geoapify_timeout", "Geoapify did not respond in time.", 504
            ) from None
        raise PlanningError(
            "geoapify_unavailable", "Geoapify could not be reached.", 502
        ) from None
    except (ValueError, OSError):
        raise PlanningError(
            "geoapify_invalid_response",
            "Geoapify returned an invalid response.",
            502,
        ) from None


def _geocode(query):
    key = _cache_key("geoapify-geocode", query.casefold())
    cached = cache.get(key)
    if cached is not None:
        return cached

    _, data = geoapify_request(
        "geocode/search",
        {"text": query, "filter": "countrycode:us", "limit": 1, "format": "json"},
    )
    try:
        result = data["results"][0]
        if result["country_code"].lower() != "us" or result.get("result_type") in {
            "country", "state", "county"
        }:
            raise IndexError
        location = Location(
            result["formatted"],
            (float(result["lon"]), float(result["lat"])),
        )
    except IndexError:
        raise PlanningError(
            "location_not_found", f"No US location matched {query!r}."
        ) from None
    except (KeyError, TypeError, ValueError, AttributeError):
        raise PlanningError(
            "geoapify_invalid_response",
            "Geoapify returned an invalid geocoding response.",
            502,
        ) from None

    cache.set(key, location, GEOCODE_TTL)
    return location


def _route(start, finish):
    cache_key = _cache_key("geoapify-route", (start.point, finish.point))
    cached = cache.get(cache_key)
    if cached is not None:
        return Route(start, finish, *cached)
    if start.point == finish.point:
        return Route(start, finish, (start.point, finish.point), 0.0, 0.0)

    waypoints = "|".join(
        f"{lat},{lon}" for lon, lat in (start.point, finish.point)
    )
    _, data = geoapify_request(
        "routing",
        {
            "waypoints": waypoints,
            "mode": "drive",
            "units": "metric",
            "format": "geojson",
        },
        routing=True,
    )
    try:
        feature = data["features"][0]
        geometry = feature["geometry"]
        segments = geometry["coordinates"]
        if geometry["type"] == "LineString":
            segments = [segments]
        elif geometry["type"] != "MultiLineString":
            raise ValueError
        coordinates = tuple(
            (float(lon), float(lat))
            for segment in segments
            for lon, lat in segment
        )
        miles = float(feature["properties"]["distance"]) / METERS_PER_MILE
        seconds = float(feature["properties"]["time"])
        if len(coordinates) < 2 or not (
            miles >= 0 and seconds >= 0 and isfinite(miles) and isfinite(seconds)
        ):
            raise ValueError
        if not all(
            -180 <= lon <= 180 and -90 <= lat <= 90 for lon, lat in coordinates
        ):
            raise ValueError
    except (IndexError, KeyError, TypeError, ValueError, AttributeError):
        raise PlanningError(
            "geoapify_invalid_response",
            "Geoapify returned invalid route geometry.",
            502,
        ) from None

    value = (coordinates, miles, seconds)
    cache.set(cache_key, value, ROUTE_TTL)
    return Route(start, finish, *value)


def get_route(start, finish):
    """Geocode both endpoints, then request one driving route."""
    _api_key()
    if start.casefold() == finish.casefold():
        location = _geocode(start)
        return _route(location, location)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(_geocode, start)
        last = pool.submit(_geocode, finish)
        return _route(first.result(), last.result())
