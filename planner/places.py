import re

STATES = frozenset("""
AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO
MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY
""".split())


def city_key(city, state):
    city = city.casefold().strip()
    city = re.sub(r"^ft\b", "fort", city)
    city = re.sub(r"^st\b", "saint", city)
    return re.sub(r"[^a-z0-9]", "", city), state.strip().upper()
