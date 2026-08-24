"""카카오 로컬 키워드 검색으로 장소명을 좌표로 바꾼다 (여행 루트 지도용)."""

import re
from typing import Literal

import httpx

from app.config import settings
from app.schemas import (
    GeoPlace, PlaceCandidate, PlaceSearchResult, ReverseGeocodeResult,
    TravelRoutePlan,
)


KAKAO_LOCAL_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
KAKAO_REVERSE_URL = "https://dapi.kakao.com/v2/local/geo/coord2regioncode.json"


def search_places(query: str, size: int = 5) -> PlaceSearchResult:
    """장소 검색은 후보가 없어도 오류 대신 빈 목록과 안내를 반환한다."""
    if not settings.kakao_rest_key:
        return PlaceSearchResult(
            query=query, note="KAKAO_REST_KEY가 없어 장소 검색을 건너뛰었습니다."
        )
    try:
        response = httpx.get(
            KAKAO_LOCAL_URL,
            params={"query": query, "size": size},
            headers={"Authorization": f"KakaoAK {settings.kakao_rest_key}"},
            timeout=5,
        )
        response.raise_for_status()
        candidates = [
            PlaceCandidate(
                name=item["place_name"],
                address=item.get("road_address_name") or item.get("address_name", ""),
                lat=float(item["y"]),
                lng=float(item["x"]),
                category=item.get("category_name", ""),
            )
            for item in response.json().get("documents", [])
        ]
        return PlaceSearchResult(query=query, candidates=candidates)
    except Exception:
        return PlaceSearchResult(
            query=query, note="카카오 장소 검색에 실패해 빈 결과를 반환했습니다."
        )


def reverse_geocode(lat: float, lng: float) -> ReverseGeocodeResult:
    """GPS 좌표를 사람이 읽을 수 있는 행정동 주소로 바꾼다 (fail-soft)."""
    empty = ReverseGeocodeResult(lat=lat, lng=lng)
    if not settings.kakao_rest_key:
        empty.note = "KAKAO_REST_KEY가 없어 좌표 변환을 건너뛰었습니다."
        return empty
    try:
        response = httpx.get(
            KAKAO_REVERSE_URL,
            params={"x": lng, "y": lat},
            headers={"Authorization": f"KakaoAK {settings.kakao_rest_key}"},
            timeout=5,
        )
        response.raise_for_status()
        documents = response.json().get("documents", [])
        document = next(
            (item for item in documents if item.get("region_type") == "H"), None
        )
        if document is None:
            empty.note = "해당 좌표의 행정동 정보를 찾지 못했습니다."
            return empty
        return ReverseGeocodeResult(
            lat=lat,
            lng=lng,
            address=document.get("address_name", ""),
            region=document.get("region_1depth_name", ""),
        )
    except Exception:
        empty.note = "카카오 좌표 변환에 실패해 빈 결과를 반환했습니다."
        return empty


def geocode_place(
    query: str,
    name: str,
    kind: Literal["landmark", "food"],
    day: int,
    order: int,
) -> GeoPlace | None:
    candidates = search_places(query, size=1).candidates
    if not candidates:
        return None
    candidate = candidates[0]
    return GeoPlace(
        name=name,
        kind=kind,
        day=day,
        order=order,
        lat=candidate.lat,
        lng=candidate.lng,
        address=candidate.address,
    )


BRANCH_SUFFIX = re.compile(r"\s*\S*점$")  # "남포동본점", "본점", "남천점" 같은 지점 접미사


def _geocode_with_fallback(
    destination: str, name: str, kind: Literal["landmark", "food"], day: int, order: int
) -> GeoPlace | None:
    """LLM이 지점명을 살짝 틀리는 일이 잦아(예: '신창국밥 남포동본점' vs 실제 '신창국밥 본점')
    전체 이름으로 못 찾으면 지점 접미사를 떼고 딱 한 번 더 검색한다."""
    place = geocode_place(f"{destination} {name}", name, kind, day, order)
    if place:
        return place
    stripped = BRANCH_SUFFIX.sub("", name).strip()
    if stripped and stripped != name:
        return geocode_place(f"{destination} {stripped}", name, kind, day, order)
    return None


def geocode_plan(plan: TravelRoutePlan) -> tuple[list[GeoPlace], list[str]]:
    """계획의 모든 장소를 지오코딩한다. 실패한 곳은 not_found로 분리 (fail-soft)."""
    places: list[GeoPlace] = []
    not_found: list[str] = []
    for landmark in plan.landmarks:
        place = _geocode_with_fallback(
            plan.destination, landmark.name, "landmark", landmark.day, landmark.visit_order
        )
        places.append(place) if place else not_found.append(landmark.name)
    for food in plan.foods:
        place = _geocode_with_fallback(plan.destination, food.name, "food", food.day, 0)
        places.append(place) if place else not_found.append(food.name)
    return places, not_found
