from dataclasses import dataclass
from time import perf_counter
from typing import Any

from app.config import settings
from app.data.cities import KOREA_CITIES
from app.schemas import (
    FoodItem, LandmarkItem, StructuredSchemaName, SupportTicket, TravelPlan,
    TravelRoutePlan,
)


@dataclass
class ProviderResult:
    provider: str
    model: str
    content: str | dict[str, Any]
    latency_ms: int


def generate_mock(system_prompt: str, message: str) -> ProviderResult:
    return ProviderResult(
        "mock", "deterministic-travel-mock", f"[Mock 응답] 질문을 확인했습니다: {message}", 0
    )


def get_structured_model(
    schema_type: StructuredSchemaName,
) -> type[TravelPlan] | type[SupportTicket] | type[TravelRoutePlan]:
    return {
        "travel_plan": TravelPlan,
        "support_ticket": SupportTicket,
        "travel_route": TravelRoutePlan,
    }[schema_type]


def generate_structured_mock(
    system_prompt: str, message: str, schema_type: StructuredSchemaName
) -> ProviderResult:
    if schema_type == "support_ticket":
        category = (
            "billing"
            if any(word in message for word in ("결제", "환불", "청구"))
            else "technical"
        )
        ticket = SupportTicket(
            category=category,
            priority="medium",
            summary="담당 팀의 확인이 필요한 고객 문의입니다.",
            requires_human=True,
            missing_information=(
                ["주문 번호"] if category == "billing" else ["오류 발생 시각"]
            ),
        )
        return ProviderResult(
            "mock", "deterministic-support-mock", ticket.model_dump(), 0
        )
    mentioned_cities = [city.name for city in KOREA_CITIES if city.name in message]
    destination = (
        min(mentioned_cities, key=message.index) if mentioned_cities else "부산"
    )
    if schema_type == "travel_route":
        route = TravelRoutePlan(
            destination=destination,
            nights=2,
            days=3,
            summary=f"{destination} 핵심 명소와 맛집을 도는 교육용 2박 3일 루트입니다.",
            landmarks=[
                LandmarkItem(name=f"{destination}역", summary="여행의 시작점", category="교통", day=1, visit_order=1, stay_minutes=30, tip="짐 보관소를 활용하세요."),
                LandmarkItem(name=f"{destination}시립미술관", summary="대표 문화 공간", category="문화", day=1, visit_order=2, stay_minutes=90, tip="휴관일을 확인하세요."),
                LandmarkItem(name=f"{destination}타워", summary="전망 명소", category="전망대", day=2, visit_order=1, stay_minutes=60, tip="야경 시간대를 추천합니다."),
            ],
            foods=[
                FoodItem(name=f"{destination} 전통시장 국밥", cuisine="한식", signature_menu="국밥", price_range="1만원 이하", day=1, meal_time="점심", near_landmark=f"{destination}역"),
                FoodItem(name=f"{destination} 회센터", cuisine="해산물", signature_menu="모둠회", price_range="3~5만원", day=2, meal_time="저녁", near_landmark=f"{destination}타워"),
            ],
        )
        return ProviderResult("mock", "deterministic-travel-mock", route.model_dump(), 0)
    plan = TravelPlan(
        destination=destination,
        summary=f"{destination}의 대표 장소를 둘러보는 교육용 일정입니다.",
        recommended_days=3,
        activities=["지역 명소 방문", "현지 음식 체험"],
        cautions=["실제 예약 전 가격과 운영 시간을 확인하세요."],
    )
    return ProviderResult("mock", "deterministic-travel-mock", plan.model_dump(), 0)


def generate_openai(system_prompt: str, message: str) -> ProviderResult:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    started = perf_counter()
    response = client.responses.create(
        model=settings.openai_model, instructions=system_prompt, input=message
    )
    return ProviderResult(
        "openai", settings.openai_model, response.output_text,
        round((perf_counter() - started) * 1000),
    )


def generate_structured_openai(
    system_prompt: str, message: str, schema_type: StructuredSchemaName
) -> ProviderResult:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    started = perf_counter()
    response = client.responses.parse(
        model=settings.openai_model,
        instructions=system_prompt,
        input=message,
        text_format=get_structured_model(schema_type),
    )
    parsed = response.output_parsed
    if parsed is None:
        raise RuntimeError("OpenAI가 구조화된 결과를 반환하지 않았습니다.")
    return ProviderResult(
        "openai", settings.openai_model, parsed.model_dump(),
        round((perf_counter() - started) * 1000),
    )


def generate_gemini(system_prompt: str, message: str) -> ProviderResult:
    client, types = _gemini_client()
    started = perf_counter()
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=message,
        config=types.GenerateContentConfig(system_instruction=system_prompt),
    )
    return ProviderResult(
        "gemini", settings.gemini_model, response.text or "",
        round((perf_counter() - started) * 1000),
    )


def _gemini_safe_schema(model_class: type) -> dict:
    # Gemini는 $defs 객체 리스트가 2개 이상인 스키마에서 minItems/maxItems를
    # 400으로 거부한다 — 생성용 스키마에서만 제거하고 개수 검증은 Pydantic이 한다.
    def strip(node: Any) -> Any:
        if isinstance(node, dict):
            return {
                k: strip(v) for k, v in node.items()
                if k not in ("minItems", "maxItems")
            }
        if isinstance(node, list):
            return [strip(v) for v in node]
        return node

    return strip(model_class.model_json_schema())


def generate_structured_gemini(
    system_prompt: str, message: str, schema_type: StructuredSchemaName
) -> ProviderResult:
    client, types = _gemini_client()
    model_class = get_structured_model(schema_type)
    started = perf_counter()
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=message,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            # response_schema는 Pydantic의 additionalProperties(extra="forbid")를
            # Gemini API가 거부하므로 raw JSON 스키마 경로를 사용한다.
            response_json_schema=_gemini_safe_schema(model_class),
        ),
    )
    parsed = model_class.model_validate_json(response.text or "{}")
    return ProviderResult(
        "gemini", settings.gemini_model, parsed.model_dump(),
        round((perf_counter() - started) * 1000),
    )


def _gemini_client() -> tuple[Any, Any]:
    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다.")
    if not settings.gemini_model:
        raise ValueError("GEMINI_MODEL이 설정되지 않았습니다.")
    from google import genai
    from google.genai import types

    return genai.Client(api_key=settings.gemini_api_key), types


def _ollama_chat(system_prompt: str, message: str, format_: dict | None = None) -> dict:
    import httpx

    payload: dict[str, Any] = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
        "stream": False,
    }
    if format_ is not None:
        payload["format"] = format_
    response = httpx.post(
        f"{settings.ollama_base_url}/api/chat",
        json=payload,
        timeout=settings.request_timeout_seconds,
    )
    response.raise_for_status()
    return response.json()


def generate_ollama(system_prompt: str, message: str) -> ProviderResult:
    started = perf_counter()
    body = _ollama_chat(system_prompt, message)
    return ProviderResult(
        "ollama", settings.ollama_model, body["message"]["content"],
        round((perf_counter() - started) * 1000),
    )


def generate_structured_ollama(
    system_prompt: str, message: str, schema_type: StructuredSchemaName
) -> ProviderResult:
    started = perf_counter()
    model_class = get_structured_model(schema_type)
    body = _ollama_chat(system_prompt, message, model_class.model_json_schema())
    parsed = model_class.model_validate_json(body["message"]["content"])
    return ProviderResult(
        "ollama", settings.ollama_model, parsed.model_dump(),
        round((perf_counter() - started) * 1000),
    )


def generate(provider: str, system_prompt: str, message: str) -> ProviderResult:
    handlers = {
        "mock": generate_mock,
        "gemini": generate_gemini,
        "openai": generate_openai,
        "ollama": generate_ollama,
    }
    if provider not in handlers:
        raise ValueError(f"지원하지 않는 Provider입니다: {provider}")
    return handlers[provider](system_prompt, message)


def generate_structured(
    provider: str,
    system_prompt: str,
    message: str,
    schema_type: StructuredSchemaName = "travel_plan",
) -> ProviderResult:
    handlers = {
        "mock": generate_structured_mock,
        "gemini": generate_structured_gemini,
        "openai": generate_structured_openai,
        "ollama": generate_structured_ollama,
    }
    if provider not in handlers:
        raise ValueError(f"지원하지 않는 Provider입니다: {provider}")
    return handlers[provider](system_prompt, message, schema_type)


def provider_status() -> list[dict]:
    return [
        {"provider": "mock", "configured": True, "model": "deterministic-structured-mock", "environment": "local-python"},
        {"provider": "gemini", "configured": bool(settings.gemini_api_key and settings.gemini_model), "model": settings.gemini_model or "(GEMINI_MODEL 미설정)", "environment": "cloud"},
        {"provider": "openai", "configured": bool(settings.openai_api_key), "model": settings.openai_model, "environment": "cloud"},
        {"provider": "ollama", "configured": True, "model": settings.ollama_model, "base_url": settings.ollama_base_url, "environment": "local-docker"},
    ]
