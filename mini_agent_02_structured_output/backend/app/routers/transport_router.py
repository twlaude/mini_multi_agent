from dataclasses import asdict
import json
from typing import Any

from fastapi import APIRouter
from pydantic import ValidationError

from app.config import settings
from app.providers import generate, select_tool
from app.schemas import (
    ToolCompleteResult, ToolRunRequest, ToolRunResult, ToolSelectionResult,
    TravelTransportRequest,
)
from app.tools.definitions import get_tool_definitions
from app.tools.transport_tools import run_tool


transport_router = APIRouter(tags=["02 · 여행 교통 Tool Use"])


@transport_router.get("/api/tools")
def tools() -> dict:
    return {
        "tools": get_tool_definitions(),
        "note": "모든 Tool은 조회 전용이며 예약이나 결제를 실행하지 않습니다.",
    }


def _run_tool_safely(tool_name: str, arguments: dict) -> ToolRunResult:
    try:
        return ToolRunResult(
            success=True, tool_name=tool_name, data=run_tool(tool_name, arguments)
        )
    except PermissionError as error:
        return ToolRunResult(
            success=False, tool_name=tool_name,
            error={"code": "TOOL_NOT_ALLOWED", "message": str(error)},
        )
    except ValidationError as error:
        details = [
            {
                "field": ".".join(map(str, item["loc"])),
                "message": item["msg"], "type": item["type"],
            }
            for item in error.errors()
        ]
        return ToolRunResult(
            success=False, tool_name=tool_name,
            error={"code": "TOOL_VALIDATION_ERROR", "details": details},
        )
    except Exception as error:
        return ToolRunResult(
            success=False, tool_name=tool_name,
            error={"code": "TOOL_EXECUTION_ERROR", "message": str(error)},
        )


@transport_router.post("/api/tools/run", response_model=ToolRunResult)
def execute_tool(payload: ToolRunRequest) -> ToolRunResult:
    return _run_tool_safely(payload.tool_name, payload.arguments)


def _mock_answer(tool_name: str, data: Any) -> str:
    if tool_name == "get_transit_route":
        options = data.get("options", []) if isinstance(data, dict) else []
        if not options:
            return data.get("note", "조회 가능한 대중교통 경로가 없습니다.")
        parts = []
        for option in options:
            hours, minutes = divmod(option["minutes"], 60)
            duration = f"{hours}시간 {minutes}분" if hours else f"{minutes}분"
            parts.append(
                f'{option["label"]} {option["from"]}→{option["to"]} '
                f'{duration} {option["fare_krw"]:,}원'
            )
        return " / ".join(parts)
    if not isinstance(data, dict):
        return "조회 가능한 자가용 경로가 없습니다."
    if data.get("distance_km") is None:
        return data.get("note", "조회 가능한 자가용 경로가 없습니다.")
    return (
        f'자가용 약 {data["minutes"]}분, {data["distance_km"]}km, '
        f'톨비 {data["toll_krw"]:,}원과 예상 유류비 {data["fuel_krw"]:,}원으로 '
        f'합계 {data["total_krw"]:,}원입니다.'
    )


@transport_router.post("/api/travel/transport", response_model=ToolCompleteResult)
def complete_transport(payload: TravelTransportRequest) -> ToolCompleteResult:
    selected = payload.provider or settings.llm_provider
    try:
        decision = ToolSelectionResult.model_validate(
            asdict(select_tool(selected, payload.message, payload.tool_choice))
        )
    except Exception as error:
        decision = ToolSelectionResult(
            provider=selected, model="tool-selection-error", tool_name=None,
            reason=f"Tool 선택 실패: {type(error).__name__}", confidence=0,
        )
        return ToolCompleteResult(
            provider=selected, question=payload.message, decision=decision,
            final_answer="교통편 Tool을 선택하지 못했습니다. Provider 설정을 확인해 주세요.",
            trace=[{"stage": "tool_selection", "data": decision.model_dump(mode="json")}],
        )

    trace = [{"stage": "tool_selection", "data": decision.model_dump(mode="json")}]
    if decision.tool_name is None:
        answer = (
            "Tool 사용이 비활성화되어 교통편을 조회하지 않았습니다."
            if payload.tool_choice == "none"
            else "질문에서 교통편 Tool을 고르지 못했습니다. "
            "'KTX로 가면?' 또는 '차로 가면?'처럼 물어보세요."
        )
        return ToolCompleteResult(
            provider=selected, question=payload.message, decision=decision,
            final_answer=answer, trace=trace,
        )

    arguments = dict(decision.arguments)
    for field in ("origin_lat", "origin_lng", "dest_lat", "dest_lng", "departure_time"):
        arguments.pop(field, None)
    arguments.update({
        "origin_lat": payload.origin.lat, "origin_lng": payload.origin.lng,
        "dest_lat": payload.destination.lat, "dest_lng": payload.destination.lng,
    })
    if payload.departure_time:
        arguments["departure_time"] = payload.departure_time.isoformat()
    if decision.tool_name == "get_driving_route":
        arguments.setdefault("fuel_efficiency_kmpl", settings.fuel_efficiency_kmpl)
        arguments.setdefault("fuel_price_per_liter", settings.fuel_price_per_liter)
    decision.arguments = arguments
    trace.append({
        "stage": "argument_injection",
        "data": {"source": "request_body", "arguments": arguments},
    })

    tool_result = _run_tool_safely(decision.tool_name, arguments)
    trace.append({"stage": "tool_result", "data": tool_result.model_dump(mode="json")})
    if not tool_result.success:
        answer = "교통편 Tool을 안전하게 실행하지 못했습니다. 입력과 설정을 확인해 주세요."
    elif selected == "mock":
        answer = _mock_answer(decision.tool_name, tool_result.data)
    else:
        prompt = (
            f"사용자 질문: {payload.message}\nTool 이름: {decision.tool_name}\n"
            f"Tool Result: {json.dumps(tool_result.data, ensure_ascii=False)}"
        )
        try:
            answer = str(generate(
                selected,
                "Tool Result에 있는 값만 사용해 친절한 한국어 답변을 작성하세요.",
                prompt,
            ).content)
        except Exception as error:
            answer = f"Tool 실행은 성공했지만 최종 답변 생성에 실패했습니다: {type(error).__name__}"

    trace.append({"stage": "final_answer", "data": {"text": answer}})
    return ToolCompleteResult(
        provider=selected, question=payload.message, decision=decision,
        tool_result=tool_result, final_answer=answer, trace=trace,
    )
