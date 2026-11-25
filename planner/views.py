from rest_framework.response import Response
from rest_framework.views import APIView

from .domain import PlanningError
from .serializers import RouteRequestSerializer
from .service import plan_route


class RoutePlanView(APIView):
    def post(self, request):
        serializer = RouteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            return Response(plan_route(**serializer.validated_data))
        except PlanningError as error:
            return Response(
                {"error": {"code": error.code, "message": str(error)}},
                status=error.status,
            )
