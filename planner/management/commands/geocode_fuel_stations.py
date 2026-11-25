"""Replace approximate station coordinates with Geoapify geocoding results."""

import csv
from math import isfinite
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import sleep

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from planner.catalog import FIELDS
from planner.domain import PlanningError
from planner.providers import geoapify_request

ACCEPTED_TYPES = {"amenity", "building", "street"}


def station_query(row):
    parts = (row["name"], row["address"], row["city"], row["state"], "USA")
    return ", ".join(part.strip() for part in parts if part.strip())


def accepted_coordinates(result, expected_state, minimum_confidence):
    """Return validated coordinates and precision, or ``None``."""
    try:
        rank = result["rank"]
        confidence = float(rank["confidence"])
        result_type = result["result_type"]
        lon, lat = float(result["lon"]), float(result["lat"])
        valid = (
            result["country_code"].lower() == "us"
            and result["state_code"].upper() == expected_state.upper()
            and result_type in ACCEPTED_TYPES
            and confidence >= minimum_confidence
            and isfinite(lon)
            and isfinite(lat)
            and -180 <= lon <= 180
            and -90 <= lat <= 90
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    if not valid:
        return None
    return lon, lat, f"geoapify_{result_type}"


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="", dir=path.parent, delete=False
    ) as stream:
        temporary = Path(stream.name)
        try:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
            stream.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def write_failures(path, failures):
    fields = ("id", "name", "address", "city", "state", "query")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(failures)


class Command(BaseCommand):
    help = "Geocode fuel stations once with Geoapify's batch API."

    def add_arguments(self, parser):
        parser.add_argument("--input", type=Path, default=settings.FUEL_STATIONS_PATH)
        parser.add_argument("--output", type=Path)
        parser.add_argument("--batch-size", type=int, default=1000)
        parser.add_argument("--max-records", type=int, default=0)
        parser.add_argument("--min-confidence", type=float, default=0.60)
        parser.add_argument("--poll-seconds", type=float, default=60)
        parser.add_argument("--max-polls", type=int, default=100)

    def handle(self, *args, **options):
        source = options["input"]
        output = options["output"] or source
        batch_size = options["batch_size"]
        limit = options["max_records"]
        confidence = options["min_confidence"]

        if not 1 <= batch_size <= 1000:
            raise CommandError("--batch-size must be between 1 and 1000.")
        if limit < 0:
            raise CommandError("--max-records cannot be negative.")
        if not 0 <= confidence <= 1:
            raise CommandError("--min-confidence must be between 0 and 1.")

        try:
            with source.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                if not set(FIELDS).issubset(reader.fieldnames or ()):
                    raise CommandError("The station catalog has invalid headers.")
                rows = list(reader)
        except OSError as exc:
            raise CommandError(str(exc)) from exc

        pending = [
            index for index, row in enumerate(rows)
            if not row["precision"].startswith("geoapify_")
        ]
        if limit:
            pending = pending[:limit]
        if not pending:
            self.stdout.write(self.style.SUCCESS("No stations need geocoding."))
            return

        matched = 0
        failures = []
        try:
            for offset in range(0, len(pending), batch_size):
                indices = pending[offset:offset + batch_size]
                queries = [station_query(rows[index]) for index in indices]
                results = self._geocode_batch(queries, options)
                if len(results) != len(indices):
                    raise CommandError("Geoapify returned an incomplete batch.")

                for index, query, result in zip(indices, queries, results):
                    row = rows[index]
                    coordinates = accepted_coordinates(result, row["state"], confidence)
                    if coordinates is None:
                        failures.append({
                            "id": row["id"], "name": row["name"],
                            "address": row["address"], "city": row["city"],
                            "state": row["state"], "query": query,
                        })
                        continue
                    lon, lat, precision = coordinates
                    row["longitude"] = str(lon)
                    row["latitude"] = str(lat)
                    row["precision"] = precision
                    matched += 1

                write_rows(output, rows)
                self.stdout.write(
                    f"Processed {min(offset + len(indices), len(pending))}/{len(pending)} stations."
                )
        except PlanningError as exc:
            raise CommandError(str(exc)) from exc

        report = output.with_name(output.stem + "-geocoding-unmatched.csv")
        write_failures(report, failures)
        self.stdout.write(self.style.SUCCESS(
            f"Updated {matched} stations; {len(failures)} results were rejected. "
            f"Review {report}."
        ))

    def _geocode_batch(self, queries, options):
        status, data = geoapify_request(
            "batch/geocode/search",
            {"filter": "countrycode:us"},
            method="POST",
            body=queries,
        )
        if status == 200:
            return data
        if status != 202 or not isinstance(data, dict) or not data.get("id"):
            raise CommandError("Geoapify did not accept the geocoding batch.")

        for _ in range(options["max_polls"]):
            sleep(options["poll_seconds"])
            status, result = geoapify_request(
                "batch/geocode/search",
                {"id": data["id"], "format": "json"},
            )
            if status == 200:
                return result
            if status != 202:
                raise CommandError("Geoapify could not finish the geocoding batch.")
        raise CommandError("Timed out waiting for Geoapify's geocoding batch.")
