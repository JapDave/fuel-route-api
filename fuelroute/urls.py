from django.urls import path

from planner.views import RoutePlanView

urlpatterns = [
    path("api/v1/route/", RoutePlanView.as_view(), name="route-plan"),
]
