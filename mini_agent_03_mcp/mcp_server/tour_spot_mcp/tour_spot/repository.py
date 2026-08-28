"""한국관광공사 TourAPI를 호출하고 관광지 결과를 정리합니다."""

from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

import httpx

from .config import TourSpotSettings
from .schemas import TourSpot, TourSpotSearchResult


TOURIST_ATTRACTION_CONTENT_TYPE = "12"


class TourApiError(RuntimeError):
    """TourAPI 호출 또는 응답 처리에 실패했을 때 발생합니다."""


class AmbiguousLocationError(ValueError):
    """같은 이름의 국내 지역이 둘 이상 발견됐을 때 발생합니다."""


@dataclass(frozen=True)
class Region:
    code: str
    name: str


@dataclass(frozen=True)
class ResolvedLocation:
    label: str
    area_code: str | None
    sigungu_code: str | None = None


# TourAPI의 광역시도 코드는 고정하고, 시군구 코드는 areaCode2에서 조회합니다.
REGIONS: tuple[Region, ...] = (
    Region("1", "서울특별시"),
    Region("2", "인천광역시"),
    Region("3", "대전광역시"),
    Region("4", "대구광역시"),
    Region("5", "광주광역시"),
    Region("6", "부산광역시"),
    Region("7", "울산광역시"),
    Region("8", "세종특별자치시"),
    Region("31", "경기도"),
    Region("32", "강원특별자치도"),
    Region("33", "충청북도"),
    Region("34", "충청남도"),
    Region("35", "경상북도"),
    Region("36", "경상남도"),
    Region("37", "전북특별자치도"),
    Region("38", "전라남도"),
    Region("39", "제주특별자치도"),
)


REGION_ALIASES: dict[str, str] = {
    "서울": "1",
    "서울시": "1",
    "서울특별시": "1",
    "인천": "2",
    "인천시": "2",
    "인천광역시": "2",
    "대전": "3",
    "대전시": "3",
    "대전광역시": "3",
    "대구": "4",
    "대구시": "4",
    "대구광역시": "4",
    "광주": "5",
    "광주시": "5",
    "광주광역시": "5",
    "부산": "6",
    "부산시": "6",
    "부산광역시": "6",
    "울산": "7",
    "울산시": "7",
    "울산광역시": "7",
    "세종": "8",
    "세종시": "8",
    "세종특별자치시": "8",
    "경기": "31",
    "경기도": "31",
    "강원": "32",
    "강원도": "32",
    "강원특별자치도": "32",
    "충북": "33",
    "충청북도": "33",
    "충남": "34",
    "충청남도": "34",
    "경북": "35",
    "경상북도": "35",
    "경남": "36",
    "경상남도": "36",
    "전북": "37",
    "전라북도": "37",
    "전북특별자치도": "37",
    "전남": "38",
    "전라남도": "38",
    "제주": "39",
    "제주도": "39",
    "제주특별자치도": "39",
}


NATIONWIDE_ALIASES = {"대한민국", "한국", "전국", "국내"}


API_ERROR_MESSAGES = {
    "01": "공공데이터 서버에서 오류가 발생했습니다.",
    "04": "공공데이터 요청 주소 또는 방식을 확인해 주세요.",
    "05": "공공데이터 서버 응답 시간이 초과됐습니다.",
    "10": "공공데이터 요청값이 올바르지 않습니다.",
    "12": "요청한 공공데이터 서비스가 존재하지 않습니다.",
    "20": "API 인증키와 활용신청 상태를 확인해 주세요.",
    "22": "공공데이터 API의 일일 호출량을 초과했습니다.",
    "23": "공공데이터 API를 너무 빠르게 호출했습니다.",
    "29": "공공데이터 API에서 현재 접속 IP를 차단했습니다.",
    "30": "등록되지 않은 API 인증키입니다.",
    "31": "API 인증키의 사용 기한이 만료됐습니다.",
}


def _compact(value: str) -> str:
    return "".join(value.split())


def _district_key(value: str) -> str:
    compact = _compact(value)
    for suffix in ("특별자치시", "특별자치도", "광역시", "시", "군", "구"):
        if compact.endswith(suffix) and len(compact) > len(suffix):
            return compact[: -len(suffix)]
    return compact


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _items_from_body(body: dict[str, Any]) -> list[dict[str, Any]]:
    items_container = body.get("items")
    if not isinstance(items_container, dict):
        return []
    items = items_container.get("item", [])
    if isinstance(items, dict):
        return [items]
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    return []


class TourSpotRepository:
    def __init__(
        self,
        settings: TourSpotSettings,
        client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings
        self.client = client
        self._district_cache: dict[str, list[Region]] = {}

    def _request(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.service_key:
            raise TourApiError(
                "TOUR_API_SERVICE_KEY가 없습니다. .env에 API 인증키를 입력해 주세요."
            )

        # 공공데이터포털의 Encoding 키와 Decoding 키를 모두 받을 수 있게 한 번 풉니다.
        common_params = {
            "serviceKey": unquote(self.settings.service_key),
            "MobileOS": "ETC",
            "MobileApp": "mini-agent-tour-spot",
            "_type": "json",
        }
        request_params = {**common_params, **params}
        url = f"{self.settings.api_base_url}/{endpoint}"

        try:
            if self.client is not None:
                response = self.client.get(url, params=request_params)
            else:
                response = httpx.get(
                    url,
                    params=request_params,
                    timeout=self.settings.api_timeout,
                )
            response.raise_for_status()
        except httpx.TimeoutException as error:
            raise TourApiError("공공데이터 API 응답 시간이 초과됐습니다.") from error
        except httpx.HTTPError as error:
            raise TourApiError(f"공공데이터 API 연결에 실패했습니다: {error}") from error

        try:
            payload = response.json()
        except ValueError as error:
            raise TourApiError(
                "공공데이터 API가 JSON이 아닌 응답을 반환했습니다. API 키와 주소를 확인해 주세요."
            ) from error

        response_payload = payload.get("response")
        if not isinstance(response_payload, dict):
            raise TourApiError("공공데이터 API 응답 형식을 확인할 수 없습니다.")

        header = response_payload.get("header", {})
        result_code = str(header.get("resultCode", ""))
        if result_code != "0000":
            result_message = str(header.get("resultMsg", "알 수 없는 오류"))
            friendly = API_ERROR_MESSAGES.get(
                result_code,
                "공공데이터 API 요청에 실패했습니다.",
            )
            raise TourApiError(f"{friendly} ({result_code}: {result_message})")

        body = response_payload.get("body", {})
        if not isinstance(body, dict):
            raise TourApiError("공공데이터 API의 body 형식이 올바르지 않습니다.")
        return body

    def _districts(self, area_code: str) -> list[Region]:
        cached = self._district_cache.get(area_code)
        if cached is not None:
            return cached

        body = self._request(
            "areaCode2",
            {
                "areaCode": area_code,
                "numOfRows": 100,
                "pageNo": 1,
            },
        )
        districts = [
            Region(str(item.get("code", "")), str(item.get("name", "")))
            for item in _items_from_body(body)
            if item.get("code") and item.get("name")
        ]
        self._district_cache[area_code] = districts
        return districts

    def _match_district(
        self,
        region: Region,
        district_text: str,
    ) -> ResolvedLocation | None:
        target = _district_key(district_text)
        for district in self._districts(region.code):
            if _district_key(district.name) == target:
                return ResolvedLocation(
                    label=f"{region.name} {district.name}",
                    area_code=region.code,
                    sigungu_code=district.code,
                )
        return None

    def resolve_location(self, location: str) -> ResolvedLocation | None:
        compact = _compact(location)
        if not compact:
            raise ValueError("location은 빈 문자열일 수 없습니다.")
        if compact in NATIONWIDE_ALIASES:
            return ResolvedLocation("대한민국 전국", None)

        direct_region_code = REGION_ALIASES.get(compact)
        if direct_region_code:
            region = next(item for item in REGIONS if item.code == direct_region_code)
            return ResolvedLocation(region.name, region.code)

        # "강원특별자치도 강릉시"처럼 상위 지역이 포함되면 해당 지역만 조회합니다.
        for alias in sorted(REGION_ALIASES, key=len, reverse=True):
            if compact.startswith(alias) and compact != alias:
                region_code = REGION_ALIASES[alias]
                region = next(item for item in REGIONS if item.code == region_code)
                district_text = compact[len(alias):]
                return self._match_district(region, district_text)

        # "경주", "강릉"처럼 시군구만 입력한 경우 전국 시군구에서 찾습니다.
        matches: list[ResolvedLocation] = []
        for region in REGIONS:
            match = self._match_district(region, compact)
            if match:
                matches.append(match)

        if len(matches) > 1:
            labels = ", ".join(match.label for match in matches)
            raise AmbiguousLocationError(
                f"'{location}'과 같은 이름의 지역이 여러 곳입니다: {labels}. "
                "시도명을 함께 입력해 주세요."
            )
        return matches[0] if matches else None

    def search(self, location: str, limit: int = 5) -> TourSpotSearchResult:
        normalized_location = location.strip()
        if not normalized_location:
            raise ValueError("location은 빈 문자열일 수 없습니다.")
        if not 1 <= limit <= 10:
            raise ValueError("limit은 1~10 범위여야 합니다.")

        resolved = self.resolve_location(normalized_location)
        if resolved is None:
            return TourSpotSearchResult(
                location=normalized_location,
                count=0,
                items=[],
                message=(
                    "국내 지역코드에서 찾을 수 없습니다. 대한민국 국내 지역명을 "
                    "확인해 주세요. 해외 관광지는 지원하지 않습니다."
                ),
            )

        params: dict[str, Any] = {
            "contentTypeId": TOURIST_ATTRACTION_CONTENT_TYPE,
            "numOfRows": limit,
            "pageNo": 1,
        }
        if resolved.area_code:
            params["areaCode"] = resolved.area_code
        if resolved.sigungu_code:
            params["sigunguCode"] = resolved.sigungu_code

        body = self._request("areaBasedList2", params)
        spots = [
            TourSpot(
                content_id=str(item.get("contentid", "")),
                name=str(item.get("title", "")).strip(),
                address=_optional_text(item.get("addr1")),
                image_url=_optional_text(item.get("firstimage")),
                latitude=_optional_float(item.get("mapy")),
                longitude=_optional_float(item.get("mapx")),
            )
            for item in _items_from_body(body)
            if item.get("contentid") and item.get("title")
        ]

        return TourSpotSearchResult(
            location=normalized_location,
            resolved_location=resolved.label,
            count=len(spots),
            items=spots,
            message=None if spots else "해당 지역에서 관광지 검색 결과를 찾지 못했습니다.",
        )
