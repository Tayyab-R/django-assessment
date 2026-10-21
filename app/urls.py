from django.urls import include, path
from rest_framework import routers

from app.views import PlanRouteView, RouteMapView

urlpatterns = [
    path("route/", PlanRouteView.as_view(), name="plan-route"),
    path("map/<str:map_id>/", RouteMapView.as_view(), name="route-map"),
]