from planner.management.commands.geocode_fuel_stations import (
    accepted_coordinates,
    station_query,
)

from django.test import SimpleTestCase


class StationGeocodingTests(SimpleTestCase):
    def result(self, **changes):
        value = {
            "country_code": "us",
            "state_code": "TX",
            "result_type": "amenity",
            "lon": -96.8,
            "lat": 32.8,
            "rank": {"confidence": 0.91},
        }
        value.update(changes)
        return value

    def test_accepts_confident_result_in_expected_state(self):
        self.assertEqual(
            accepted_coordinates(self.result(), "TX", 0.60),
            (-96.8, 32.8, "geoapify_amenity"),
        )

    def test_rejects_wrong_state_low_confidence_and_city_only_results(self):
        self.assertIsNone(
            accepted_coordinates(self.result(state_code="OK"), "TX", 0.60)
        )
        self.assertIsNone(
            accepted_coordinates(
                self.result(rank={"confidence": 0.59}), "TX", 0.60
            )
        )
        self.assertIsNone(
            accepted_coordinates(self.result(result_type="city"), "TX", 0.60)
        )

    def test_query_contains_the_station_address_and_country(self):
        query = station_query({
            "name": "Example Fuel",
            "address": "I-35, Exit 10",
            "city": "Dallas",
            "state": "TX",
        })
        self.assertEqual(query, "Example Fuel, I-35, Exit 10, Dallas, TX, USA")
