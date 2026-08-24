from app.schemas import DrivingRoutePreference, TransitRoutePreference


TRANSPORT_TOOL_DEFINITIONS = [
    {
        "name": "get_transit_route",
        "description": (
            "출발지와 목적지 사이의 기차, 버스, 항공 대중교통을 조회합니다. "
            "출발지·도착지 좌표와 출발 시각은 서버가 이미 알고 있으므로 넣지 않습니다."
        ),
        "input_schema": TransitRoutePreference.model_json_schema(),
    },
    {
        "name": "get_driving_route",
        "description": (
            "출발지와 목적지 사이의 자가용 경로와 톨비, 예상 유류비를 조회합니다. "
            "출발지·도착지 좌표와 출발 시각은 서버가 이미 알고 있으므로 넣지 않습니다."
        ),
        "input_schema": DrivingRoutePreference.model_json_schema(),
    },
]


def get_tool_definitions() -> list[dict]:
    """조회만 가능하고 예약·결제 권한은 없는 Tool 계약을 반환합니다."""
    return TRANSPORT_TOOL_DEFINITIONS
