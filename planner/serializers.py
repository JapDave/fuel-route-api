from decimal import Decimal

from rest_framework import serializers


class LocationField(serializers.CharField):
    def to_internal_value(self, data):
        if not isinstance(data, str):
            raise serializers.ValidationError("Enter a US city or street address as text.")
        return " ".join(super().to_internal_value(data).split())


class RouteRequestSerializer(serializers.Serializer):
    start = LocationField(max_length=200)
    finish = LocationField(max_length=200)
    starting_price_per_gallon = serializers.DecimalField(
        max_digits=7, decimal_places=5, min_value=Decimal("0.00001"),
        max_value=Decimal("99"), required=False,
    )
