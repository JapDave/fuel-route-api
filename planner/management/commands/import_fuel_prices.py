import csv
import io
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import ZipFile

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from planner.catalog import FIELDS
from planner.geometry import air_miles
from planner.places import STATES, city_key

ID = "OPIS Truckstop ID"
PRICE = "Retail Price"
REQUIRED = {ID, "Truckstop Name", "Address", "City", "State", PRICE}
SUFFIX = re.compile(r" (city|town|village|borough|municipality|CDP|city and borough)$", re.I)


def census_places(path):
    with ZipFile(path) as archive:
        member = next(name for name in archive.namelist() if name.endswith(".txt"))
        with archive.open(member) as stream:
            rows = csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig"), delimiter="|")
            for row in rows:
                if row["USPS"] in STATES:
                    name = SUFFIX.sub("", row["NAME"])
                    yield name, row["USPS"], float(row["INTPTLONG"]), float(row["INTPTLAT"])


def supplemental_places(path, wanted):
    with ZipFile(path) as archive, archive.open("US.txt") as stream:
        best = {}
        for line in io.TextIOWrapper(stream, encoding="utf-8"):
            row = line.rstrip("\n").split("\t")
            if row[6] != "P" or row[7] in {"PPLX", "PPLH", "PPLQ", "PPLW"} or row[10] not in STATES:
                continue
            candidates = {city_key(value, row[10]) for value in (row[1], row[2])}
            for key in candidates & wanted:
                score = int(row[14] or 0)
                if key not in best or score > best[key][0]:
                    best[key] = (score, (float(row[5]), float(row[4])))
        return {key: entry[1] for key, entry in best.items()}


def unique_places(places):
    result = {}
    for name, state, lon, lat in places:
        key = city_key(name, state)
        point = lon, lat
        if key in result and (result[key] is None or air_miles(point, result[key]) > 5):
            # Different towns with the same name require an explicit override.
            result[key] = None
            continue
        result[key] = point
    return result


def load_overrides(path):
    if not path:
        return {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        records = {}
        for row in csv.DictReader(stream):
            lon, lat = float(row["longitude"]), float(row["latitude"])
            identifier = row["id"].strip()
            if not identifier or not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise ValueError("Invalid station coordinate override.")
            records[identifier] = lon, lat
        return records


def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent,
                            delete=False) as stream:
        temporary = Path(stream.name)
        try:
            writer = csv.writer(stream)
            writer.writerow(fields)
            writer.writerows(rows)
            stream.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


class Command(BaseCommand):
    help = "Join the supplied OPIS price sheet to offline US place coordinates."

    def add_arguments(self, parser):
        parser.add_argument("prices", type=Path)
        parser.add_argument("--gazetteer", type=Path, required=True)
        parser.add_argument("--geonames", type=Path, help="Optional GeoNames US.zip for missing towns.")
        parser.add_argument("--overrides", type=Path, help="Optional CSV with id,longitude,latitude.")
        parser.add_argument("--output", type=Path, default=settings.FUEL_STATIONS_PATH)
        parser.add_argument("--places-output", type=Path, default=settings.FUEL_PLACES_PATH)

    def handle(self, *args, **options):
        try:
            self.import_catalog(**options)
        except (OSError, ValueError, TypeError, KeyError, StopIteration, csv.Error) as exc:
            raise CommandError(str(exc)) from exc

    def import_catalog(self, prices, gazetteer, geonames, overrides: Path, output,
                       places_output, **kwargs):
        with prices.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if not REQUIRED.issubset(reader.fieldnames or ()):
                raise ValueError("Expected the OPIS assessment CSV headers.")
            rows = list(reader)

        places = unique_places(census_places(gazetteer))
        exact = load_overrides(overrides)
        if geonames:
            needed = {city_key(row["City"], row["State"]) for row in rows} - places.keys()
            places.update(supplemental_places(geonames, needed))

        stations = {}
        invalid = 0
        for row in rows:
            identifier = (row[ID] or "").strip()
            try:
                price = Decimal((row[PRICE] or "").strip().lstrip("$"))
                if not identifier or not price.is_finite() or not 0 < price < 100:
                    raise InvalidOperation
            except InvalidOperation:
                invalid += 1
                continue
            current = stations.get(identifier)
            if current is None or price < current[0]:
                stations[identifier] = price, row

        normalized = []
        missing = []
        for identifier, (price, row) in stations.items():
            key = city_key(row["City"], row["State"])
            point = exact.get(identifier) or places.get(key)
            if point is None:
                missing.append((identifier, row["Truckstop Name"], row["Address"], row["City"], row["State"]))
                continue
            precision = "station" if identifier in exact else "city_centroid"
            normalized.append((identifier, row["Truckstop Name"], row["Address"],
                               row["City"], row["State"], price, *point, precision))

        if not normalized:
            raise ValueError("No stations could be located.")
        write_csv(output, FIELDS, normalized)
        write_csv(output.with_name(output.stem + "-unmatched.csv"),
                  ("id", "name", "address", "city", "state"), missing)
        write_csv(places_output, ("city_key", "state", "longitude", "latitude"),
                  ((*key, *point) for key, point in sorted(places.items()) if point is not None))
        self.stdout.write(self.style.SUCCESS(
            f"{len(rows)} price rows, {len(stations)} unique valid IDs, "
            f"{len(normalized)} stations loaded, {len(missing)} missing locations, "
            f"{invalid} invalid rows."
        ))
