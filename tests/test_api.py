import json
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from planner.domain import Location, PlanningError, Route
from planner import providers

DALLAS = Location("Dallas, TX, USA", (-96.7970, 32.7767))
DENVER = Location("Denver, CO, USA", (-104.9903, 39.7392))
ROUTE_LINE = (
    DALLAS.point,
    (-97.1331, 33.2148),
    (-97.1564, 34.1743),
    (-97.5164, 35.4676),
    (-98.9673, 35.5156),
    (-101.8313, 35.2220),
    (-102.5170, 36.0609),
    (-103.1850, 36.4517),
    (-104.4392, 36.9034),
    (-104.5005, 37.1695),
    (-104.6091, 38.2544),
    (-104.8214, 38.8339),
    DENVER.point,
)


@override_settings(GEOAPIFY_API_KEY="test-key")
class RouteApiTests(SimpleTestCase):
    def post(self, route=None, **payload):
        route = route or Route(DALLAS, DENVER, ROUTE_LINE, 830.0, 46800.0)
        with patch("planner.service.get_route", return_value=route):
            return self.client.post(
                "/api/v1/route/", json.dumps(payload), content_type="application/json"
            )

    def test_returns_stops_cost_and_geojson(self):
        response = self.post(start="Dallas, TX", finish="Denver, CO")
        self.assertEqual(response.status_code, 200)
        plan = response.json()
        self.assertEqual(plan["routing_provider"], "Geoapify")
        self.assertEqual(plan["map"]["type"], "FeatureCollection")
        self.assertGreater(plan["summary"]["fuel_stop_count"], 0)
        self.assertTrue(
            all(leg <= 500 for leg in plan["summary"]["leg_distances_miles"])
        )

    def test_identical_endpoints_cost_zero(self):
        route = Route(DALLAS, DALLAS, (DALLAS.point, DALLAS.point), 0.0, 0.0)
        response = self.post(
            route=route, start="Dallas, TX", finish="Dallas, TX"
        )
        self.assertEqual(
            response.json()["summary"]["estimated_total_fuel_cost_usd"], "0.00"
        )

    def test_rejects_invalid_inputs(self):
        self.assertEqual(self.post(start=7, finish="Denver, CO").status_code, 400)
        self.assertEqual(self.post(start=" ", finish="Denver, CO").status_code, 400)
        self.assertEqual(self.post(start="Dallas, TX").status_code, 400)

    def test_returns_provider_error_as_json(self):
        error = PlanningError("geoapify_timeout", "Geoapify timed out.", 504)
        with patch("planner.service.get_route", side_effect=error):
            response = self.client.post(
                "/api/v1/route/",
                {"start": "Dallas, TX", "finish": "Denver, CO"},
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 504)
        self.assertEqual(response.json()["error"]["code"], "geoapify_timeout")


class GeoapifyProviderTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def fixture(self, path, params=None, **kwargs):
        if path == "routing":
            return 200, {"features": [{
                "geometry": {
                    "type": "MultiLineString",
                    "coordinates": [[list(DALLAS.point), list(DENVER.point)]],
                },
                "properties": {"distance": 1250000, "time": 50000},
            }]}
        query = params["text"]
        location = DALLAS if "Dallas" in query else DENVER
        return 200, {"results": [{
            "country_code": "us",
            "formatted": location.label,
            "result_type": "city",
            "lon": location.point[0],
            "lat": location.point[1],
        }]}

    @override_settings(GEOAPIFY_API_KEY="test-key")
    def test_two_geocodes_and_one_route_are_cached(self):
        with patch("planner.providers.geoapify_request", side_effect=self.fixture) as request:
            first = providers.get_route("Dallas, TX", "Denver, CO")
            second = providers.get_route("Dallas, TX", "Denver, CO")
        self.assertEqual(first, second)
        self.assertEqual(request.call_count, 3)

    @override_settings(GEOAPIFY_API_KEY="")
    def test_api_key_is_required(self):
        with self.assertRaises(PlanningError) as result:
            providers.get_route("Dallas, TX", "Denver, CO")
        self.assertEqual(result.exception.code, "geoapify_not_configured")

    @override_settings(GEOAPIFY_API_KEY="test-key")
    def test_unknown_location_is_rejected(self):
        with patch(
            "planner.providers.geoapify_request",
            return_value=(200, {"results": []}),
        ):
            with self.assertRaises(PlanningError) as result:
                providers.get_route("Unknown place", "Denver, CO")
        self.assertEqual(result.exception.code, "location_not_found")
