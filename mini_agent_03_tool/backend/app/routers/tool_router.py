from dataclasses import asdict
import json

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.config import settings
from app.providers import generate, select_tool
from app.schemas import (
    ToolCompareRequest, ToolCompareResult, ToolComparisonItem,
    ToolCompleteRequest, ToolCompleteResult, ToolRunRequest, ToolRunResult,
    ToolSelectRequest, ToolSelectionResult,
)
from app.tools.definitions import get_tool_definitions
from app.tools.travel_tools import run_tool


tool_router = APIRouter(tags=["03 · Tool Use"])


@tool_router.get("/api/tools")
def tools() -> dict:
    return {"tools": get_tool_definitions(), "note": "모든 Tool은 조회 전용이며 예약이나 결제를 실행하지 않습니다."}


@tool_router.post("/api/tools/select", response_model=ToolSelectionResult)
def choose_tool(payload: ToolSelectRequest) -> ToolSelectionResult:
    selected = payload.provider or settings.llm_provider
    try:
        return ToolSelectionResult.model_validate(asdict(select_tool(selected, payload.message, payload.tool_choice)))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"{selected} Tool 선택에 실패했습니다: {error}") from error


@tool_router.post("/api/tools/compare", response_model=ToolCompareResult)
def compare_tool_selection(payload: ToolCompareRequest) -> ToolCompareResult:
    items: list[ToolComparisonItem] = []
    for selected in payload.providers:
        try:
            decision = ToolSelectionResult.model_validate(asdict(select_tool(selected, payload.message, payload.tool_choice)))
            items.append(ToolComparisonItem(provider=selected, status="success", decision=decision))
        except Exception as error:
            items.append(ToolComparisonItem(provider=selected, status="error", error=str(error)))
    return ToolCompareResult(request_count=len(payload.providers), results=items)


@tool_router.post("/api/tools/run", response_model=ToolRunResult)
def execute_tool(payload: ToolRunRequest) -> ToolRunResult:
    return _run_tool_safely(payload.tool_name, payload.arguments)


def _run_tool_safely(tool_name: str, arguments: dict) -> ToolRunResult:
    try:
        return ToolRunResult(success=True, tool_name=tool_name, data=run_tool(tool_name, arguments))
    except PermissionError as error:
        return ToolRunResult(success=False, tool_name=tool_name, error={"code": "TOOL_NOT_ALLOWED", "message": str(error)})
    except ValidationError as error:
        details = [{"field": ".".join(map(str, item["loc"])), "message": item["msg"], "type": item["type"]} for item in error.errors()]
        return ToolRunResult(success=False, tool_name=tool_name, error={"code": "TOOL_VALIDATION_ERROR", "details": details})
    except Exception as error:
        return ToolRunResult(success=False, tool_name=tool_name, error={"code": "TOOL_EXECUTION_ERROR", "message": str(error)})


@tool_router.post("/api/tools/complete", response_model=ToolCompleteResult)
def complete_tool_loop(payload: ToolCompleteRequest) -> ToolCompleteResult:
    selected = payload.provider or settings.llm_provider
    try:
        decision = ToolSelectionResult.model_validate(asdict(select_tool(selected, payload.message, payload.tool_choice)))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"{selected} Tool 선택 실패: {error}") from error

    trace = [{"stage": "tool_selection", "data": decision.model_dump(mode="json")}]
    if decision.needs_clarification:
        trace.append({
            "stage": "clarification",
            "data": {
                "missing_arguments": decision.missing_arguments,
                "follow_up_question": decision.follow_up_question,
            },
        })
        return ToolCompleteResult(provider=selected, question=payload.message, decision=decision, final_answer=decision.follow_up_question, trace=trace)

    if decision.tool_name is None:
        final_answer = "이 질문에는 실행할 조회 Tool이 필요하지 않습니다."
        trace.append({"stage": "finish", "data": {"reason": "no_tool"}})
        return ToolCompleteResult(provider=selected, question=payload.message, decision=decision, final_answer=final_answer, trace=trace)

    tool_result = _run_tool_safely(decision.tool_name, decision.arguments)
    trace.append({"stage": "tool_result", "data": tool_result.model_dump(mode="json")})
    if not tool_result.success:
        return ToolCompleteResult(
            provider=selected,
            question=payload.message,
            decision=decision,
            tool_result=tool_result,
            final_answer="Tool을 안전하게 실행하지 못했습니다. 입력과 권한을 확인해 주세요.",
            trace=trace,
        )

    if selected == "mock":
        final_answer = f"{decision.tool_name} 조회 결과입니다: {json.dumps(tool_result.data, ensure_ascii=False)}"
    else:
        prompt = (
            f"사용자 질문: {payload.message}\n"
            f"Tool 이름: {decision.tool_name}\n"
            f"Tool Result: {json.dumps(tool_result.data, ensure_ascii=False)}"
        )
        system_prompt = "Tool Result에 있는 값만 사용해 사용자에게 친절한 한국어 최종 답변을 작성하세요."
        try:
            final_answer = str(generate(selected, system_prompt, prompt).content)
        except Exception as error:
            final_answer = f"Tool 실행은 성공했지만 최종 답변 생성에 실패했습니다: {error}"

    return ToolCompleteResult(
        provider=selected,
        question=payload.message,
        decision=decision,
        tool_result=tool_result,
        final_answer=final_answer,
        trace=trace + [{"stage": "final_answer", "data": {"text": final_answer}}],
    )
