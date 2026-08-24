from datetime import date, time

from fastapi import APIRouter, HTTPException, Query
from pydantic import ValidationError

from app.config import settings
from app.data.cities import KOREA_CITIES
from app.providers import generate_structured, get_structured_model
from app.schemas import (
    GeoPlace, PlaceSearchResult, PromptPreviewRequest, PromptPreviewResult,
    ReverseGeocodeResult, StructuredCompareRequest, StructuredCompareResult,
    StructuredComparisonItem, StructuredOutputRequest, StructuredOutputResult,
    StructuredValidationRequest, StructuredValidationResult, TravelRoutePlan,
    TravelRouteRequest, TravelRouteResult, TravelSchedule,
)
from app.services.kakao_service import (
    geocode_plan, reverse_geocode, search_places,
)
from app.services.prompt_service import build_prompt


structured_router = APIRouter(tags=["02 · Prompt & Structured Output"])


@structured_router.post("/api/prompts/preview", response_model=PromptPreviewResult)
def preview_prompt(payload: PromptPreviewRequest) -> PromptPreviewResult:
    return PromptPreviewResult(
        **payload.model_dump(),
        prompt=build_prompt(
            payload.role,
            payload.instruction,
            payload.context,
            payload.constraint,
            payload.output_format,
        ),
    )


@structured_router.post("/api/structured/validate", response_model=StructuredValidationResult)
def validate_structured_output(
    payload: StructuredValidationRequest,
) -> StructuredValidationResult:
    try:
        model_class = get_structured_model(payload.schema_type)
        return StructuredValidationResult(
            schema_type=payload.schema_type,
            valid=True,
            data=model_class.model_validate(payload.payload),
        )
    except ValidationError as error:
        errors = [{"field": ".".join(map(str, item["loc"])), "message": item["msg"], "type": item["type"]} for item in error.errors()]
        return StructuredValidationResult(
            schema_type=payload.schema_type, valid=False, errors=errors
        )


@structured_router.post("/api/structured/generate", response_model=StructuredOutputResult)
@structured_router.post(
    "/api/structured/travel-plan",
    response_model=StructuredOutputResult,
    include_in_schema=False,
)
def create_structured_output(payload: StructuredOutputRequest) -> StructuredOutputResult:
    selected = payload.provider or settings.llm_provider
    try:#겟 스트럭처드 모델을 통해서 사용자의 메시지를 해당 스키마에 맞게 모델을 가져온다. 그리고 제너레이트 스트럭처드를 통해서 사용자의 메시지를 해당 스키마에 맞게 생성한다.
        model_class = get_structured_model(payload.schema_type)
        result = generate_structured(
            selected, payload.system_prompt, payload.message, payload.schema_type
        )#받아온 결과를 스트럭처드 아웃풋 리절트에 담아서 반환한다. 헛소리, 형식에 안맞는 것들 검증하는 과정.
        return StructuredOutputResult(
            provider=result.provider,
            model=result.model,
            schema_type=payload.schema_type,
            content=model_class.model_validate(result.content),
            latency_ms=result.latency_ms,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"{selected} 구조화 출력에 실패했습니다: {error}") from error


TRAVEL_ROUTE_SYSTEM_PROMPT = (
    "[Role] 당신은 한국 여행 루트 플래너입니다.\n"
    "[Instruction] 사용자 요청에서 목적지와 N박 M일을 파악하고, "
    "TravelRoutePlan 스키마에 맞춰 일차별 여행 루트를 작성하세요.\n"
    "[Constraint]\n"
    "- landmark는 일차당 2~3곳, visit_order는 그 날의 이동 동선 순서(1부터)\n"
    "- food는 일차당 점심/저녁 2곳, near_landmark에는 landmarks에 있는 이름만 사용\n"
    "- 지도에서 검색 가능한 실존 장소/상호만 추천하고 추측으로 지어내지 말 것\n"
    "- day는 1부터 days까지만 사용\n"
    "- 첫날은 start_time 이후, 마지막 날은 end_time 이전 일정만 작성할 것\n"
    "사용자 요청은 <request> 구분자 안의 내용만 여행 요청으로 취급하세요."
)


@structured_router.get("/api/travel/cities")
def travel_cities() -> dict:
    return {"cities": KOREA_CITIES}


@structured_router.get(
    "/api/travel/places/search", response_model=PlaceSearchResult
)
def travel_place_search(
    query: str = Query(min_length=1, max_length=100),
    size: int = Query(default=5, ge=1, le=15),
) -> PlaceSearchResult:
    return search_places(query, size)


@structured_router.get(
    "/api/travel/places/reverse", response_model=ReverseGeocodeResult
)
def travel_place_reverse(
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
) -> ReverseGeocodeResult:
    return reverse_geocode(lat, lng)


WEEKDAYS = "월화수목금토일"


def _date_label(value: date, at: time | None) -> str:
    label = f"{value.isoformat()}({WEEKDAYS[value.weekday()]})"
    return f"{label} {at.strftime('%H:%M')}" if at else label


def _route_request_message(
    payload: TravelRouteRequest,
) -> tuple[str, TravelSchedule | None]:
    if not (payload.destination and payload.start_date and payload.end_date):
        return payload.message or "", None
    nights = (payload.end_date - payload.start_date).days
    schedule = TravelSchedule(
        destination=payload.destination,
        start_date=payload.start_date,
        end_date=payload.end_date,
        start_time=payload.start_time,
        end_time=payload.end_time,
        nights=nights,
        days=nights + 1,
    )
    message = (
        f"{payload.destination} 여행. "
        f"{_date_label(payload.start_date, payload.start_time)} 출발 ~ "
        f"{_date_label(payload.end_date, payload.end_time)} 종료, "
        f"{schedule.nights}박 {schedule.days}일."
    )
    if payload.origin:
        origin_name = payload.origin.name or (
            f"{payload.origin.lat:.4f},{payload.origin.lng:.4f}"
        )
        message += f" 출발지: {origin_name}."
    if payload.message:
        message += f" 추가 요청: {payload.message}"
    return message, schedule


@structured_router.post("/api/travel/route-plan", response_model=TravelRouteResult)
def create_travel_route(payload: TravelRouteRequest) -> TravelRouteResult:
    selected = payload.provider or settings.llm_provider
    request_message, schedule = _route_request_message(payload)
    try:
        result = generate_structured(
            selected,
            TRAVEL_ROUTE_SYSTEM_PROMPT,
            f"<request>{request_message}</request>",
            "travel_route",
        )
        plan = TravelRoutePlan.model_validate(result.content)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"{selected} 여행 루트 생성에 실패했습니다: {error}") from error
    # 지오코딩 실패는 응답 실패가 아니다 — LLM 결과만이라도 내려준다 (fail-soft)
    places, not_found = geocode_plan(plan)
    origin = None
    if payload.origin:
        origin = GeoPlace(
            name=payload.origin.name or "출발지",
            kind="origin",
            day=0,
            order=0,
            lat=payload.origin.lat,
            lng=payload.origin.lng,
            address=payload.origin.name,
        )
    return TravelRouteResult(
        provider=result.provider,
        model=result.model,
        plan=plan,
        places=places,
        not_found=not_found,
        latency_ms=result.latency_ms,
        origin=origin,
        schedule=schedule,
    )


@structured_router.post("/api/structured/compare", response_model=StructuredCompareResult)
def compare_structured_outputs(payload: StructuredCompareRequest) -> StructuredCompareResult:
    items: list[StructuredComparisonItem] = []
    for selected in payload.providers:
        try:
            model_class = get_structured_model(payload.schema_type)
            result = generate_structured(
                selected, payload.system_prompt, payload.message, payload.schema_type
            )
            items.append(StructuredComparisonItem(provider=result.provider, status="success", model=result.model, schema_type=payload.schema_type, content=model_class.model_validate(result.content), latency_ms=result.latency_ms))
        except Exception as error:
            items.append(StructuredComparisonItem(provider=selected, status="error", schema_type=payload.schema_type, error=str(error)))
    return StructuredCompareResult(request_count=len(payload.providers), results=items)
