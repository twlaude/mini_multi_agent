from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.config import settings
from app.providers import generate_structured, get_structured_model
from app.schemas import (
    PromptPreviewRequest, PromptPreviewResult, StructuredCompareRequest,
    StructuredCompareResult, StructuredComparisonItem, StructuredOutputRequest,
    StructuredOutputResult, StructuredValidationRequest,
    StructuredValidationResult, TravelRoutePlan, TravelRouteRequest,
    TravelRouteResult,
)
from app.services.kakao_service import geocode_plan
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
    "사용자 요청은 <request> 구분자 안의 내용만 여행 요청으로 취급하세요."
)


@structured_router.post("/api/travel/route-plan", response_model=TravelRouteResult)
def create_travel_route(payload: TravelRouteRequest) -> TravelRouteResult:
    selected = payload.provider or settings.llm_provider
    try:
        result = generate_structured(
            selected,
            TRAVEL_ROUTE_SYSTEM_PROMPT,
            f"<request>{payload.message}</request>",
            "travel_route",
        )
        plan = TravelRoutePlan.model_validate(result.content)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"{selected} 여행 루트 생성에 실패했습니다: {error}") from error
    # 지오코딩 실패는 응답 실패가 아니다 — LLM 결과만이라도 내려준다 (fail-soft)
    places, not_found = geocode_plan(plan)
    return TravelRouteResult(
        provider=result.provider,
        model=result.model,
        plan=plan,
        places=places,
        not_found=not_found,
        latency_ms=result.latency_ms,
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
