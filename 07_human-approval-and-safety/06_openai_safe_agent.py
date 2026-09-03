"""OpenAI 기반 여행 AI Agent가 사용자 승인을 받아 일정을 저장하는 예제입니다.

상황:
사용자가 "제주 날씨에 맞는 여행 장소를 찾아 일정으로 저장해 줘"라고 요청합니다.
Agent는 OpenAI Model의 판단으로 날씨와 장소를 조회하고 일정 초안까지 만들 수
있습니다. 그러나 일정 저장은 외부 상태를 변경하므로 바로 실행하지 않고 사용자에게
승인 여부를 묻습니다.

실행 흐름:
사용자 요청
→ OpenAI가 날씨 Tool 선택 및 실행
→ Tool Result를 받은 OpenAI가 장소 검색 Tool 선택 및 실행
→ OpenAI가 여행 일정 저장 Tool 제안
→ Backend가 Tool 이름과 arguments를 State에 저장하고 실행 중단
→ 터미널에서 사용자에게 승인 여부 입력 요청
   ├─ y: 승인 대상을 확인하고 Mock 일정 저장
   └─ n: 아무것도 저장하지 않고 종료
→ 저장 Result를 OpenAI에 전달하여 최종 답변 생성

Model이 ``save_itinerary``를 선택했다는 사실은 실행 권한을 의미하지 않습니다.
Model은 행동을 제안하고 Backend가 승인 필요 여부와 실제 실행을 통제합니다.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

INSTRUCTIONS = """당신은 여행 일정 저장 AI Agent입니다.
먼저 get_weather와 search_places로 근거를 확인한 뒤 save_itinerary를 호출하세요.
Tool Result에 없는 사실은 만들지 마세요. Tool 실행 권한은 Backend 정책이 결정합니다.
"""

TOOLS = [
    {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        },
        "strict": True,
    }
    for name, description, properties in (
        ("get_weather", "도시의 날씨를 조회합니다.", {"city": {"type": "string"}}),
        ("search_places", "도시의 추천 장소를 조회합니다.", {"city": {"type": "string"}}),
        (
            "save_itinerary",
            "여행 일정을 저장합니다. 외부 상태를 변경하므로 승인이 필요합니다.",
            {"city": {"type": "string"}, "place": {"type": "string"}},
        ),
    )
]

TOOL_RISK = {"get_weather": "read", "search_places": "read", "save_itinerary": "change"}
PROCESSED_CALLS: set[str] = set()
AUDIT_LOG: list[dict[str, Any]] = []


@dataclass
class SafeAgentState:
    """OpenAI 응답과 Human Approval 사이를 연결하는 실행 State입니다.

    ``previous_response_id``와 ``pending_call``은 승인 후 같은 Function Call에 Result를
    돌려주기 위해 필요합니다. Tool Call 전체를 승인 Snapshot으로 보관하여 사용자가
    확인한 대상과 실제 실행 대상이 달라지지 않게 합니다.
    """
    run_id: str
    owner_id: str
    question: str
    status: str = "running"
    previous_response_id: str | None = None
    pending_call: dict[str, Any] | None = None
    trace: list[dict[str, Any]] = field(default_factory=list)


def require_client() -> OpenAI:
    """API Key를 확인한 뒤 동기 OpenAI Client를 생성합니다."""
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("과정 루트의 .env에 OPENAI_API_KEY를 설정하세요.")
    return OpenAI()


def execute_read_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """자동 실행이 허용된 읽기 Tool만 Allowlist 방식으로 실행합니다.

    변경 Tool인 ``save_itinerary``는 이 함수가 처리하지 않습니다. Model이 변경 Tool을
    제안하면 ``run_until_approval``이 실행 대신 State에 저장하고 사용자 승인을 요청합니다.
    """
    if name == "get_weather":
        return {"city": arguments["city"], "condition": "비", "temperature_c": 21}
    if name == "search_places":
        return {"city": arguments["city"], "items": ["제주현대미술관", "아쿠아플라넷"]}
    raise ValueError(f"자동 실행할 수 없는 Tool입니다: {name}")


def run_until_approval(state: SafeAgentState, max_steps: int = 6) -> dict[str, Any]:
    """OpenAI Tool Calling을 반복하고 변경 Tool 직전에 실행을 중단합니다.

    읽기 Tool은 Backend가 검증 후 실행하여 Result를 Model에 전달합니다. 변경 Tool은
    이름, arguments와 call_id를 승인 Snapshot으로 저장하고 ``waiting_approval``을
    반환합니다. 허용되지 않은 Tool, 잘못된 arguments와 최대 단계 초과는 차단합니다.
    """
    client = require_client()
    response = client.responses.create(
        model=MODEL,
        instructions=INSTRUCTIONS,
        input=state.question,
        tools=TOOLS,
        tool_choice="auto",
        parallel_tool_calls=False,
    )
    for step in range(1, max_steps + 1):
        calls = [item for item in response.output if item.type == "function_call"]
        if not calls:
            state.status = "completed"
            return {"status": state.status, "answer": response.output_text, "trace": state.trace}
        call = calls[0]
        if call.name not in TOOL_RISK:
            state.status = "blocked"
            return {"status": state.status, "reason": "TOOL_NOT_ALLOWED"}
        try:
            arguments = json.loads(call.arguments)
        except (AttributeError, json.JSONDecodeError, TypeError):
            state.status = "blocked"
            return {"status": state.status, "reason": "INVALID_TOOL_ARGUMENTS"}
        if not isinstance(arguments, dict):
            state.status = "blocked"
            return {"status": state.status, "reason": "INVALID_TOOL_ARGUMENTS"}
        risk = TOOL_RISK[call.name]
        state.trace.append({"step": step, "tool": call.name, "arguments": arguments, "risk": risk})
        if risk == "change":
            approval_target = {"tool": call.name, "arguments": arguments}
            state.status = "waiting_approval"
            state.previous_response_id = response.id
            state.pending_call = {"call_id": call.call_id, "tool": call.name, "arguments": arguments}
            return {
                "status": state.status,
                "question": "이 여행 일정을 저장할까요?",
                "approval_target": approval_target,
                "trace": state.trace,
            }
        result = execute_read_tool(call.name, arguments)
        response = client.responses.create(
            model=MODEL,
            instructions=INSTRUCTIONS,
            previous_response_id=response.id,
            input=[
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(result, ensure_ascii=False),
                }
            ],
            tools=TOOLS,
            tool_choice="auto",
            parallel_tool_calls=False,
        )
    state.status = "blocked"
    return {"status": state.status, "reason": "MAX_STEPS_EXCEEDED", "trace": state.trace}


def resume_after_approval(
    state: SafeAgentState,
    actor: str,
    decision: str,
    approval_target: dict[str, Any],
) -> dict[str, Any]:
    """사용자 결정을 검증하고 승인된 변경 Result로 OpenAI Agent를 재개합니다.

    Args:
        state: 변경 Tool Call과 이전 OpenAI response id가 저장된 승인 대기 State입니다.
        actor: 운영 환경에서는 인증 Session에서 얻어야 하는 승인자 식별자입니다.
        decision: ``approve`` 또는 ``reject`` 구조화 결정입니다.
        approval_target: 사용자에게 표시했던 Tool 이름과 arguments Snapshot입니다.

    Returns:
        거절·차단·중복 또는 완료 결과를 반환합니다. 승인된 경우에만 Mock 변경을 한 번
        실행하고 Function Call Output을 Model에 전달해 최종 답변을 생성합니다.
    """
    if state.status != "waiting_approval" or not state.pending_call:
        return {"status": "blocked", "reason": "NOT_WAITING_APPROVAL"}
    if actor != state.owner_id:
        return {"status": "blocked", "reason": "ACTOR_NOT_OWNER"}
    if decision not in {"approve", "reject"}:
        return {"status": "blocked", "reason": "INVALID_DECISION"}
    expected = {"tool": state.pending_call["tool"], "arguments": state.pending_call["arguments"]}
    if approval_target != expected:
        return {"status": "blocked", "reason": "APPROVAL_TARGET_CHANGED"}
    if decision == "reject":
        state.status = "rejected"
        state.trace.append({"stage": "approval", "decision": "reject", "actor": actor})
        return {"status": state.status, "reason": "USER_REJECTED", "trace": state.trace}

    key = f"{state.run_id}:{state.pending_call['call_id']}"
    if key in PROCESSED_CALLS:
        return {"status": "completed", "reason": "ALREADY_PROCESSED"}
    if state.pending_call["tool"] != "save_itinerary":
        return {"status": "blocked", "reason": "CHANGE_TOOL_NOT_ALLOWED"}

    # 실제 서비스에서는 이 지점이 예약·저장 API 호출이 됩니다. 이번 장에서는 승인 이후
    # 다음 단계로 진행한다는 사실에 집중하기 위해 관찰 가능한 Mock Result만 만듭니다.
    result = {"saved": True, **state.pending_call["arguments"]}
    PROCESSED_CALLS.add(key)
    audit = {"run_id": state.run_id, "actor": actor, "approval_target": expected, "result": result}
    AUDIT_LOG.append(audit)
    state.trace.extend(
        [
            {"stage": "approval", "decision": "approve", "actor": actor},
            {"stage": "tool_result", "tool": "save_itinerary", "data": result},
        ]
    )
    state.status = "completed"
    try:
        response = require_client().responses.create(
            model=MODEL,
            instructions=INSTRUCTIONS,
            previous_response_id=state.previous_response_id,
            input=[
                {
                    "type": "function_call_output",
                    "call_id": state.pending_call["call_id"],
                    "output": json.dumps(result, ensure_ascii=False),
                }
            ],
            tools=TOOLS,
            tool_choice="auto",
            parallel_tool_calls=False,
        )
    except Exception as error:
        return {
            "status": state.status,
            "termination_reason": "completed_with_answer_error",
            "result": result,
            "audit": audit,
            "answer": None,
            "answer_error": str(error),
        }
    return {
        "status": state.status,
        "termination_reason": "completed",
        "answer": response.output_text,
        "result": result,
        "audit": audit,
        "trace": state.trace,
    }


def ask_user_decision() -> str:
    """터미널에서 사용자가 y 또는 n을 입력할 때까지 승인 여부를 묻습니다."""

    while True:
        answer = input("일정을 저장할까요? [y/n]: ").strip().lower()
        if answer in {"y", "yes", "승인"}:
            return "approve"
        if answer in {"n", "no", "거절"}:
            return "reject"
        print("y(승인) 또는 n(거절)을 입력해 주세요.")


if __name__ == "__main__":
    agent_state = SafeAgentState(
        run_id="openai-safe-001",
        owner_id="user-01",
        question="제주 날씨에 맞는 장소를 찾아 여행 일정으로 저장해 줘.",
    )
    paused = run_until_approval(agent_state)
    print("승인 대기:", json.dumps(paused, ensure_ascii=False, indent=2))
    if paused["status"] == "waiting_approval":
        decision = ask_user_decision()
        target = paused["approval_target"]
        completed = resume_after_approval(agent_state, "user-01", decision, target)
        print("처리 결과:", json.dumps(completed, ensure_ascii=False, indent=2))
