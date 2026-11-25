import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "django-insecure-local-development-only")
DEBUG = os.environ.get("DJANGO_DEBUG") == "1"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
ROOT_URLCONF = "fuelroute.urls"
INSTALLED_APPS = ["rest_framework", "planner"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware",
              "django.middleware.common.CommonMiddleware"]
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "APP_DIRS": True,
}]
CACHES = {"default": {
    "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    "LOCATION": "routing",
    "OPTIONS": {"MAX_ENTRIES": 128},
}}
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
}
GEOAPIFY_API_KEY = os.environ.get("GEOAPIFY_API_KEY", "")
FUEL_STATIONS_PATH = BASE_DIR / os.environ.get("FUEL_STATIONS_PATH", "data/stations.csv")
# The application is read-only. Its station catalog is an indexed CSV.
DATABASES = {}
FUEL_PLACES_PATH = BASE_DIR / os.environ.get("FUEL_PLACES_PATH", "data/places.csv")
