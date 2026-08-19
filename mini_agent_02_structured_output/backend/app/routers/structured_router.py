from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.config import settings
from app.providers import generate_structured, get_structured_model
from app.schemas import (
    PromptPreviewRequest, PromptPreviewResult, StructuredCompareRequest,
    StructuredCompareResult, StructuredComparisonItem, StructuredOutputRequest,
    StructuredOutputResult, StructuredValidationRequest,
    StructuredValidationResult,
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
    try:
        model_class = get_structured_model(payload.schema_type)
        result = generate_structured(
            selected, payload.system_prompt, payload.message, payload.schema_type
        )
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
