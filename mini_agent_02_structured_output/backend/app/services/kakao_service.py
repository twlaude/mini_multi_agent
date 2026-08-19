"""카카오 로컬 키워드 검색으로 장소명을 좌표로 바꾼다 (여행 루트 지도용)."""

from typing import Literal

import httpx

from app.config import settings
from app.schemas import GeoPlace, TravelRoutePlan


KAKAO_LOCAL_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"


def geocode_place(
    query: str,
    name: str,
    kind: Literal["landmark", "food"],
    day: int,
    order: int,
) -> GeoPlace | None:
    if not settings.kakao_rest_key:
        return None
    try:
        response = httpx.get(
            KAKAO_LOCAL_URL,
            params={"query": query, "size": 1},
            headers={"Authorization": f"KakaoAK {settings.kakao_rest_key}"},
            timeout=5,
        )
        response.raise_for_status()
        documents = response.json().get("documents", [])
    except Exception:
        return None
    if not documents:
        return None
    document = documents[0]
    return GeoPlace(
        name=name,
        kind=kind,
        day=day,
        order=order,
        lat=float(document["y"]),
        lng=float(document["x"]),
        address=document.get("road_address_name") or document.get("address_name", ""),
    )


def geocode_plan(plan: TravelRoutePlan) -> tuple[list[GeoPlace], list[str]]:
    """계획의 모든 장소를 지오코딩한다. 실패한 곳은 not_found로 분리 (fail-soft)."""
    places: list[GeoPlace] = []
    not_found: list[str] = []
    for landmark in plan.landmarks:
        place = geocode_place(
            f"{plan.destination} {landmark.name}", landmark.name,
            "landmark", landmark.day, landmark.visit_order,
        )
        places.append(place) if place else not_found.append(landmark.name)
    for food in plan.foods:
        place = geocode_place(
            f"{plan.destination} {food.name}", food.name, "food", food.day, 0
        )
        places.append(place) if place else not_found.append(food.name)
    return places, not_found
