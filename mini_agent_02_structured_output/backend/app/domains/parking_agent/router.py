from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.domains.parking_agent.agent_service import (
    agent_note,
    ask_agent,
    list_tailgating,
    list_visitors,
    run_agent,
)
from app.domains.parking_agent.schemas import AgentGateRequest, AskRequest


parking_agent_router = APIRouter(prefix="/parking/agent", tags=["Parking Agent"])


def _error(message: str) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": message, "data": None},
    )


@parking_agent_router.post("/gate")
def gate(payload: AgentGateRequest) -> Any:
    try:
        decision = run_agent(payload)
        return {
            "success": True,
            "message": "에이전트 출입 판단을 완료했습니다.",
            "data": decision.model_dump(),
        }
    except Exception as error:
        return _error(f"에이전트 출입 판단 실패: {error}")


@parking_agent_router.get("/visitors")
def visitors() -> Any:
    try:
        rows = list_visitors()
        return {
            "success": True,
            "message": "현재 주차 중인 외부인을 조회했습니다.",
            "data": {"items": rows, "agent_note": agent_note("외부인", rows)},
        }
    except Exception as error:
        return _error(f"외부인 조회 실패: {error}")


@parking_agent_router.get("/tailgating")
def tailgating() -> Any:
    try:
        rows = list_tailgating()
        return {
            "success": True,
            "message": "꼬리물기 의심 차량을 조회했습니다.",
            "data": {"items": rows, "agent_note": agent_note("꼬리물기 의심", rows)},
        }
    except Exception as error:
        return _error(f"꼬리물기 조회 실패: {error}")


@parking_agent_router.post("/ask")
def ask(payload: AskRequest) -> Any:
    try:
        result = ask_agent(payload.question)
        return {
            "success": True,
            "message": "관제 에이전트가 답변했습니다.",
            "data": result,
        }
    except Exception as error:
        return _error(f"관제 에이전트 답변 실패: {error}")
