import csv
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from math import floor, isfinite
from pathlib import Path
from statistics import median

from .domain import PlanningError, Station

CELL_DEGREES = 0.25
FIELDS = ("id", "name", "address", "city", "state", "price", "longitude", "latitude",
          "precision")


def cell(coordinate):
    return floor(coordinate / CELL_DEGREES)


@dataclass(frozen=True)
class Catalog:
    stations: tuple[Station, ...]
    grid: dict
    median_price: Decimal


@lru_cache(maxsize=4)
def _load(path: Path, modified_ns: int, size: int) -> Catalog:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = csv.DictReader(stream)
        if not set(FIELDS).issubset(rows.fieldnames or ()):
            raise ValueError("The station catalog has invalid headers.")
        records = {}
        for row in rows:
            price = Decimal(row["price"])
            lon, lat = float(row["longitude"]), float(row["latitude"])
            if not (price.is_finite() and 0 < price < 100 and isfinite(lon) and
                    isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
                raise ValueError("The station catalog contains an invalid price or coordinate.")
            station = Station(*(row[key] for key in FIELDS[:5]), price, (lon, lat),
                              row["precision"])
            if station.id not in records or price < records[station.id].price:
                records[station.id] = station
    stations = tuple(records.values())
    if not stations:
        raise ValueError("The station catalog is empty.")
    grid = defaultdict(list)
    for station in stations:
        grid[cell(station.point[0]), cell(station.point[1])].append(station)
    return Catalog(stations, dict(grid), median(station.price for station in stations))


def load_catalog(path):
    try:
        info = path.stat()
        return _load(path, info.st_mtime_ns, info.st_size)
    except (OSError, ValueError, TypeError, InvalidOperation, csv.Error) as exc:
        raise PlanningError(
            "station_catalog_unavailable",
            "A valid station catalog is required. Run import_fuel_prices first.",
            503,
        ) from exc
