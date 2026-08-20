from typing import Any

import httpx

from app.config import settings
from app.schemas import TransitRouteArgs


ODSAY_URL = "https://api.odsay.com/v1/api/searchPubTransPathT"
BASE_NOTE = "도시간 검색은 역/터미널 기준 — 역↔목적지 시내 이동은 별도"


def _empty(note: str) -> dict:
    return {"options": [], "note": note, "source": "odsay"}


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _int_or_zero(value: Any) -> int:
    return _optional_int(value) or 0


def search_transit_routes(args: TransitRouteArgs) -> dict:
    if not settings.odsay_key:
        return _empty(f"ODSAY_KEY가 없어 조회를 건너뛰었습니다. {BASE_NOTE}")
    try:
        response = httpx.get(
            ODSAY_URL,
            params={
                "apiKey": settings.odsay_key,
                "SX": args.origin_lng, "SY": args.origin_lat,
                "EX": args.dest_lng, "EY": args.dest_lat,
                "OPT": 0, "SearchType": 1, "lang": 0,
            },
            headers={"Referer": "http://localhost"},
            timeout=15,
        )
        response.raise_for_status()
        body = response.json()
    except Exception as error:
        return _empty(f"ODsay 조회 실패({type(error).__name__}). {BASE_NOTE}")

    if (
        not isinstance(body, dict)
        or body.get("error")
        or not isinstance(body.get("result"), dict)
    ):
        return _empty(f"ODsay가 경로를 반환하지 않았습니다. {BASE_NOTE}")

    options: list[dict] = []
    type_by_path = {11: "train", 12: "bus", 13: "air"}
    paths = body["result"].get("path", [])
    if not isinstance(paths, list):
        return _empty(f"ODsay 응답을 해석하지 못했습니다. {BASE_NOTE}")
    for path in paths:
        if not isinstance(path, dict):
            continue
        route_type = type_by_path.get(path.get("pathType"))
        if route_type is None or args.mode not in ("all", route_type):
            continue
        info = path.get("info") or {}
        sub_paths = path.get("subPath") or []
        if not isinstance(info, dict):
            continue
        sub = sub_paths[0] if isinstance(sub_paths, list) and sub_paths else {}
        if not isinstance(sub, dict):
            sub = {}
        traffic_type = sub.get("trafficType")
        if route_type == "train":
            label = (
                "SRT" if sub.get("trainType") == 1 and sub.get("startName") == "수서"
                else "KTX" if sub.get("trainType") == 1 else "일반열차"
            )
        else:
            label = {5: "고속버스", 6: "시외버스", 7: "항공"}.get(
                traffic_type, "버스" if route_type == "bus" else "항공"
            )
        options.append({
            "type": route_type, "label": label,
            "from": info.get("firstStartStation", ""),
            "to": info.get("lastEndStation", ""),
            "minutes": _int_or_zero(info.get("totalTime")),
            "fare_krw": _int_or_zero(info.get("totalPayment")),
            "premium_fare_krw": _optional_int(sub.get("trainSpSeatPayment")),
            "interval_min": _optional_int(sub.get("intervalTime")),
            "daily_count": _optional_int(sub.get("intervalCount")),
        })

    selected = [
        item for route_type in ("train", "bus", "air")
        for item in sorted(
            (option for option in options if option["type"] == route_type),
            key=lambda option: option["minutes"],
        )[:3]
    ]
    note = BASE_NOTE if selected else f"조건에 맞는 경로가 없습니다. {BASE_NOTE}"
    return {"options": selected, "note": note, "source": "odsay"}
