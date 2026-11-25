from math import asin, cos, hypot, pi, radians, sin, sqrt

from .catalog import cell
from .domain import Candidate

EARTH_MILES = 3958.76
CORRIDOR_MILES = 8.0
ACCESS_FACTOR = 1.3
MILES_PER_DEGREE = EARTH_MILES * pi / 180


def air_miles(a, b):
    lon1, lat1 = map(radians, a)
    lon2, lat2 = map(radians, b)
    term = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_MILES * asin(sqrt(min(1.0, term)))


def route_candidates(route, catalog):
    segments = [(a, b, air_miles(a, b)) for a, b in
                zip(route.coordinates, route.coordinates[1:]) if a != b]
    geometry_length = sum(length for _, _, length in segments)
    if not geometry_length:
        return []
    scale = route.miles / geometry_length
    best = {}
    accumulated = 0.0
    dy = CORRIDOR_MILES / MILES_PER_DEGREE
    for a, b, length in segments:
        x_scale = MILES_PER_DEGREE * max(0.01, cos(radians((a[1] + b[1]) / 2)))
        dx = CORRIDOR_MILES / x_scale
        if abs(b[0] - a[0]) > 180:
            # Avoid spanning the globe on a segment crossing the antimeridian.
            b = (b[0] + (360 if b[0] < a[0] else -360), b[1])
        x = (b[0] - a[0]) * x_scale
        y = (b[1] - a[1]) * MILES_PER_DEGREE
        length_squared = x * x + y * y
        for gx in range(cell(min(a[0], b[0]) - dx), cell(max(a[0], b[0]) + dx) + 1):
            wrapped = (gx + cell(180)) % cell(360) - cell(180)
            for gy in range(cell(min(a[1], b[1]) - dy), cell(max(a[1], b[1]) + dy) + 1):
                for station in catalog.grid.get((wrapped, gy), ()):
                    lon, lat = station.point
                    sx = ((lon - a[0] + 180) % 360 - 180) * x_scale
                    sy = (lat - a[1]) * MILES_PER_DEGREE
                    fraction = max(0.0, min(1.0, (sx * x + sy * y) / length_squared))
                    offset = hypot(sx - fraction * x, sy - fraction * y)
                    if offset > CORRIDOR_MILES:
                        continue
                    access = offset * ACCESS_FACTOR
                    existing = best.get(station.point)
                    if existing is not None:
                        old = existing
                        if (access, station.price, station.id) >= (
                            old.access_miles, old.station.price, old.station.id
                        ):
                            continue
                    mile = (accumulated + length * fraction) * scale
                    point = (((a[0] + fraction * (b[0] - a[0])) + 180) % 360 - 180,
                             a[1] + fraction * (b[1] - a[1]))
                    best[station.point] = Candidate(station, min(route.miles, mile), access, point)
        accumulated += length
    return list(best.values())
