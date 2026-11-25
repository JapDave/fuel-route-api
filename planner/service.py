from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings

from .catalog import load_catalog
from .domain import MPG, RANGE_MILES, TANK_GALLONS
from .geometry import route_candidates
from .optimizer import optimize
from .providers import get_route


def money(value):
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def feature(kind, coordinates, **properties):
    return {"type": "Feature", "geometry": {"type": kind, "coordinates": coordinates},
            "properties": properties}


def plan_route(start, finish, starting_price_per_gallon=None):
    catalog = load_catalog(settings.FUEL_STATIONS_PATH)
    route = get_route(start, finish)
    candidates = route_candidates(route, catalog) if route.miles > RANGE_MILES else []
    purchases = optimize(route.miles, candidates)

    features = [
        feature("LineString", route.coordinates, type="route"),
        feature("Point", route.start.point, type="start", label=route.start.label),
        feature("Point", route.finish.point, type="finish", label=route.finish.label),
    ]
    route_legs = []
    stops = []
    last_mile = last_access = detours = 0.0
    remaining = TANK_GALLONS
    for number, purchase in enumerate(purchases, 1):
        candidate = purchase.candidate
        station = candidate.station
        leg = candidate.mile - last_mile + last_access + candidate.access_miles
        arrival = max(0.0, remaining - leg / MPG)
        remaining = arrival + float(purchase.gallons)
        route_legs.append(round(leg, 3))
        stops.append({
            "number": number, "id": station.id, "name": station.name, "address": station.address,
            "city": station.city, "state": station.state, "coordinates": station.point,
            "location_precision": station.precision, "route_mile": round(candidate.mile, 3),
            "estimated_access_miles_one_way": round(candidate.access_miles, 3),
            "price_per_gallon_usd": str(station.price),
            "gallons_to_buy": round(float(purchase.gallons), 5),
            "gallons_on_arrival": round(arrival, 5),
            "gallons_on_departure": round(remaining, 5),
            "cost_usd": money(purchase.cost),
        })
        features.append(feature("Point", station.point, type="fuel_stop", number=number,
                                name=station.name, location_precision=station.precision))
        features.append(feature("LineString", (candidate.route_point, station.point),
                                type="estimated_station_access"))
        last_mile, last_access = candidate.mile, candidate.access_miles
        detours += 2 * candidate.access_miles
    last_leg = route.miles - last_mile + last_access
    route_legs.append(round(last_leg, 3))
    remaining = max(0.0, remaining - last_leg / MPG)

    total_miles = route.miles + detours
    consumed = Decimal(str(round(total_miles, 10))) / MPG
    initial_gallons_used = min(Decimal(str(TANK_GALLONS)), consumed)
    initial_price = starting_price_per_gallon or catalog.median_price
    start_value = initial_gallons_used * initial_price
    en_route = sum((purchase.cost for purchase in purchases), Decimal(0))

    return {
        "start": {"label": route.start.label, "coordinates": route.start.point},
        "finish": {"label": route.finish.label, "coordinates": route.finish.point},
        "summary": {
            "route_distance_miles": round(route.miles, 3),
            "estimated_detour_miles": round(detours, 3),
            "estimated_total_miles": round(total_miles, 3),
            "route_duration_minutes": round(route.seconds / 60, 1),
            "fuel_economy_mpg": MPG, "max_range_miles": RANGE_MILES,
            "starting_tank_gallons": TANK_GALLONS, "fuel_used_gallons": round(float(consumed), 5),
            "estimated_fuel_at_finish_gallons": round(remaining, 5),
            "fuel_stop_count": len(stops), "leg_distances_miles": route_legs,
            "starting_price_per_gallon_usd": str(initial_price),
            "starting_fuel_price_basis": "user_supplied" if starting_price_per_gallon is not None
                                          else "catalog_median",
            "starting_fuel_value_usd": money(start_value), "fuel_purchased_en_route_usd": money(en_route),
            "estimated_total_fuel_cost_usd": money(start_value + en_route),
        },
        "fuel_stops": stops,
        "map": {"type": "FeatureCollection", "features": features},
        "routing_provider": "Geoapify",
        "fuel_price_source": "Supplied OPIS retail-price snapshot",
    }
