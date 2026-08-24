import httpx

from app.config import settings
from app.schemas import DrivingRouteArgs


KAKAO_DIRECTIONS_URL = "https://apis-navi.kakaomobility.com/v1/directions"
KAKAO_FUTURE_URL = "https://apis-navi.kakaomobility.com/v1/future/directions"


def _empty(args: DrivingRouteArgs, note: str) -> dict:
    return {
        "distance_km": None, "minutes": None, "toll_krw": None,
        "fuel_krw": None, "taxi_krw": None, "total_krw": None,
        "assumptions": {
            "fuel_efficiency_kmpl": args.fuel_efficiency_kmpl,
            "fuel_price_per_liter": args.fuel_price_per_liter,
        },
        "note": note, "source": "kakao_mobility",
    }


def search_driving_route(args: DrivingRouteArgs) -> dict:
    if not settings.kakao_rest_key:
        return _empty(args, "KAKAO_REST_KEY가 없어 자가용 조회를 건너뛰었습니다.")
    url = KAKAO_FUTURE_URL if args.departure_time else KAKAO_DIRECTIONS_URL
    params = {
        "origin": f"{args.origin_lng},{args.origin_lat}",
        "destination": f"{args.dest_lng},{args.dest_lat}",
        "priority": "RECOMMEND",
    }
    if args.departure_time:
        params["departure_time"] = args.departure_time.strftime("%Y%m%d%H%M")
    try:
        response = httpx.get(
            url, params=params,
            headers={"Authorization": f"KakaoAK {settings.kakao_rest_key}"},
            timeout=15,
        )
        response.raise_for_status()
        routes = response.json().get("routes") or []
    except Exception as error:
        return _empty(args, f"카카오모빌리티 조회 실패({type(error).__name__}).")
    if (
        not isinstance(routes, list)
        or not routes
        or not isinstance(routes[0], dict)
        or routes[0].get("result_code") != 0
    ):
        return _empty(args, "카카오모빌리티가 정상 경로를 반환하지 않았습니다.")

    summary = routes[0].get("summary") or {}
    try:
        fare = summary.get("fare") or {}
        distance_km = float(summary.get("distance") or 0) / 1000
        toll = int(fare.get("toll") or 0)
        fuel = round(
            distance_km / args.fuel_efficiency_kmpl * args.fuel_price_per_liter
        )
        minutes = round(float(summary.get("duration") or 0) / 60)
        taxi = int(fare.get("taxi") or 0)
    except (AttributeError, TypeError, ValueError):
        return _empty(args, "카카오모빌리티 응답을 해석하지 못했습니다.")
    return {
        "distance_km": round(distance_km, 1),
        "minutes": minutes,
        "toll_krw": toll, "fuel_krw": fuel,
        "taxi_krw": taxi, "total_krw": toll + fuel,
        "assumptions": {
            "fuel_efficiency_kmpl": args.fuel_efficiency_kmpl,
            "fuel_price_per_liter": args.fuel_price_per_liter,
        },
        "source": "kakao_mobility",
    }
