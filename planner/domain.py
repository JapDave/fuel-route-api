from dataclasses import dataclass
from decimal import Decimal

Point = tuple[float, float]  # longitude, latitude
METERS_PER_MILE = 1609.344
MPG = 10
RANGE_MILES = 500.0
TANK_GALLONS = RANGE_MILES / MPG


@dataclass(frozen=True)
class Location:
    label: str
    point: Point


@dataclass(frozen=True)
class Route:
    start: Location
    finish: Location
    coordinates: tuple[Point, ...]
    miles: float
    seconds: float


@dataclass(frozen=True)
class Station:
    id: str
    name: str
    address: str
    city: str
    state: str
    price: Decimal
    point: Point
    precision: str


@dataclass(frozen=True)
class Candidate:
    station: Station
    mile: float
    access_miles: float
    route_point: Point


class PlanningError(Exception):
    def __init__(self, code, message, status=422):
        super().__init__(message)
        self.code = code
        self.status = status
