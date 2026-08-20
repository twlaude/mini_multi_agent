from collections.abc import Callable

from app.schemas import DrivingRouteArgs, TransitRouteArgs
from app.services.kakao_mobility_service import search_driving_route
from app.services.odsay_service import search_transit_routes


def get_transit_route(arguments: dict) -> dict:
    args = TransitRouteArgs.model_validate(arguments)
    return search_transit_routes(args)


def get_driving_route(arguments: dict) -> dict:
    args = DrivingRouteArgs.model_validate(arguments)
    return search_driving_route(args)


TOOLS: dict[str, Callable[[dict], dict]] = {
    "get_transit_route": get_transit_route,
    "get_driving_route": get_driving_route,
}


def run_tool(name: str, arguments: dict) -> dict:
    """모델이 고른 이름을 신뢰하지 않고 서버 allowlist 안에서만 실행합니다."""
    tool = TOOLS.get(name)
    if tool is None:
        raise PermissionError("허용되지 않은 Tool입니다.")
    return tool(arguments)
