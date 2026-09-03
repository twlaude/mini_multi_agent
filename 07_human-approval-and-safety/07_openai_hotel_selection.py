"""호텔 후보를 조회한 뒤 사용자의 선택을 받아 OpenAI Agent를 재개하는 예제입니다.

상황:
사용자가 ``부산에서 1박 15만 원 이하 호텔을 찾아 줘``라고 요청하면 Agent는 조건에
맞는 호텔을 여러 개 찾을 수 있습니다. 어느 호텔을 선택할지는 사용자의 선호이므로
Agent가 임의로 하나를 확정해서는 안 됩니다. 호텔 후보를 보여주고 사용자의 선택을
받아야 취소 정책 조회나 예약 초안 작성 같은 다음 Prompt 작업을 진행할 수 있습니다.

실행 흐름:
사용자 요청
→ OpenAI가 호텔 검색 Tool 선택 및 실행
→ 검색된 호텔 후보를 State에 저장하고 실행 중단
→ 터미널에 호텔 후보와 hotel_id 표시
→ 사용자가 원하는 hotel_id 입력
→ 입력한 hotel_id가 직전 검색 후보에 있는지 확인
→ 선택 결과를 OpenAI에 전달
→ OpenAI가 취소 정책 Tool을 실행하고 예약 초안 생성

이 상황은 ``waiting_approval``과 다릅니다. 호텔 선택은 외부 변경을 허용하는 승인이
아니라 다음 판단에 필요한 정보를 보완하는 사용자 입력이므로 ``waiting_user``입니다.
선택한 호텔로 실제 예약을 실행하려면 별도의 변경 Tool과 ``waiting_approval`` 단계가
추가로 필요합니다. 이 파일은 선택과 승인을 혼동하지 않도록 실제 예약 직전까지만
진행합니다.
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
MAX_STEPS = 5

HOTELS = [
    {"hotel_id": "hotel-busan-001", "name": "바다 호텔", "city": "부산", "price": 130_000},
    {"hotel_id": "hotel-busan-002", "name": "항구 호텔", "city": "부산", "price": 145_000},
    {"hotel_id": "hotel-seoul-001", "name": "도시 호텔", "city": "서울", "price": 120_000},
]
CANCELLATION_POLICIES = {
    "hotel-busan-001": "체크인 3일 전까지 취소하면 전액 환불합니다.",
    "hotel-busan-002": "체크인 7일 전까지 취소하면 전액 환불합니다.",
    "hotel-seoul-001": "체크인 2일 전까지 취소하면 전액 환불합니다.",
}

INSTRUCTIONS = """당신은 호텔 선택 도우미 AI Agent입니다.
먼저 search_hotels로 사용자의 조건에 맞는 후보를 조회하세요.
사용자가 선택한 hotel_id가 전달된 뒤에만 get_cancellation_policy를 호출하세요.
취소 정책을 확인한 후 선택 호텔과 정책을 포함한 예약 초안을 작성하세요.
실제 예약·결제는 실행하지 말고 Tool Result에 없는 사실을 만들지 마세요.
"""

TOOLS = [
    {
        "type": "function",
        "name": "search_hotels",
        "description": "도시와 1박 최대 가격으로 호텔 후보를 조회합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "max_price": {"type": "integer", "minimum": 1},
            },
            "required": ["city", "max_price"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_cancellation_policy",
        "description": "사용자가 선택한 호텔의 취소 정책을 조회합니다.",
        "parameters": {
            "type": "object",
            "properties": {"hotel_id": {"type": "string"}},
            "required": ["hotel_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


@dataclass
class HotelSelectionState:
    """호텔 검색과 사용자 선택 전후를 연결하는 Agent 실행 State입니다.

    검색 응답 id와 Function Call id, 후보 목록과 선택 결과를 보관합니다. 후보 목록은
    사용자가 임의의 hotel_id를 주입하지 못하게 하는 Backend 검증 근거로 사용됩니다.
    """
    run_id: str
    owner_id: str
    question: str
    status: str = "running"
    previous_response_id: str | None = None
    search_call_id: str | None = None
    hotel_candidates: list[dict[str, Any]] = field(default_factory=list)
    selected_hotel_id: str | None = None
    trace: list[dict[str, Any]] = field(default_factory=list)


def require_client() -> OpenAI:
    """과정 루트의 API Key를 확인하고 OpenAI Client를 반환합니다."""
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("과정 루트의 .env에 OPENAI_API_KEY를 설정하세요.")
    return OpenAI()


def search_hotels(city: str, max_price: int) -> dict[str, Any]:
    """도시와 가격 조건에 맞는 읽기 전용 호텔 후보를 조회합니다.

    실제 예약은 수행하지 않으며, 반환된 ``hotel_id``만 이후 사용자 선택과 정책 조회에
    사용할 수 있습니다.
    """
    items = [hotel for hotel in HOTELS if hotel["city"] == city and hotel["price"] <= max_price]
    return {"success": True, "city": city, "max_price": max_price, "items": items}


def get_cancellation_policy(hotel_id: str) -> dict[str, Any]:
    """검증된 hotel_id의 취소 정책을 조회하고 존재하지 않으면 실패 Result를 반환합니다."""
    policy = CANCELLATION_POLICIES.get(hotel_id)
    if policy is None:
        return {"success": False, "error": "HOTEL_NOT_FOUND", "hotel_id": hotel_id}
    hotel = next(hotel for hotel in HOTELS if hotel["hotel_id"] == hotel_id)
    return {
        "success": True,
        "hotel_id": hotel_id,
        "hotel_name": hotel["name"],
        "cancellation_policy": policy,
    }


def parse_arguments(call: Any) -> dict[str, Any]:
    """OpenAI Function Call arguments를 JSON Object로 파싱하고 형식을 검증합니다."""
    try:
        arguments = json.loads(call.arguments)
    except (AttributeError, json.JSONDecodeError, TypeError) as error:
        raise ValueError("Tool arguments가 올바른 JSON이 아닙니다.") from error
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments는 JSON Object여야 합니다.")
    return arguments


def run_until_hotel_selection(state: HotelSelectionState) -> dict[str, Any]:
    """OpenAI가 제안한 호텔 검색을 실행하고 사용자 선택 직전에 중단합니다.

    최초 Model 응답은 반드시 ``search_hotels``여야 합니다. 검색 결과와 OpenAI의
    response/call id를 State에 저장하고 후보가 있으면 ``waiting_user``를 반환합니다.
    후보 없음은 재질문과 구분되는 ``NO_HOTELS_FOUND`` 안전 종료입니다.
    """
    response = require_client().responses.create(
        model=MODEL,
        instructions=INSTRUCTIONS,
        input=state.question,
        tools=TOOLS,
        tool_choice="auto",
        parallel_tool_calls=False,
    )
    calls = [item for item in response.output if item.type == "function_call"]
    if not calls:
        state.status = "completed"
        return {"status": state.status, "answer": response.output_text, "trace": state.trace}

    call = calls[0]
    if call.name != "search_hotels":
        state.status = "blocked"
        return {"status": state.status, "reason": "HOTEL_SEARCH_REQUIRED", "trace": state.trace}
    arguments = parse_arguments(call)
    result = search_hotels(arguments.get("city", ""), arguments.get("max_price", 0))
    state.trace.append({"stage": "tool_result", "tool": call.name, "arguments": arguments, "result": result})
    if not result["items"]:
        state.status = "blocked"
        return {"status": state.status, "reason": "NO_HOTELS_FOUND", "trace": state.trace}

    state.status = "waiting_user"
    state.previous_response_id = response.id
    state.search_call_id = call.call_id
    state.hotel_candidates = result["items"]
    return {
        "status": state.status,
        "question": "조회된 호텔 중 하나의 hotel_id를 선택해 주세요.",
        "hotel_candidates": state.hotel_candidates,
        "allowed_hotel_ids": [hotel["hotel_id"] for hotel in state.hotel_candidates],
        "trace": state.trace,
    }


def validate_hotel_selection(state: HotelSelectionState, actor: str, hotel_id: str) -> dict[str, Any]:
    """같은 사용자가 이전 검색 결과 안의 호텔을 선택했는지 검증합니다.

    ``waiting_user`` 상태, 실행 소유자와 후보 포함 여부를 모두 검사합니다. 자연어로
    존재한다고 주장한 호텔이나 이전 검색에 없던 hotel_id는 다음 Prompt로 전달하지 않습니다.
    """
    if state.status != "waiting_user":
        return {"valid": False, "reason": "NOT_WAITING_USER"}
    if actor != state.owner_id:
        return {"valid": False, "reason": "ACTOR_NOT_OWNER"}
    selected = next((hotel for hotel in state.hotel_candidates if hotel["hotel_id"] == hotel_id), None)
    if selected is None:
        return {"valid": False, "reason": "HOTEL_NOT_IN_CANDIDATES"}
    return {"valid": True, "hotel": selected}


def resume_after_hotel_selection(
    state: HotelSelectionState,
    actor: str,
    hotel_id: str,
    max_steps: int = MAX_STEPS,
) -> dict[str, Any]:
    """선택값을 검증한 뒤 Tool Result와 사용자 선택을 OpenAI에 전달해 재개합니다.

    Args:
        state: 후보, response id와 search call id가 보관된 ``waiting_user`` State입니다.
        actor: 선택을 제출한 인증된 사용자 식별자입니다.
        hotel_id: 사용자가 직전 후보 중에서 선택한 호텔 식별자입니다.
        max_steps: 선택 이후 허용할 최대 Model·Tool 재판단 횟수입니다.

    Returns:
        잘못된 선택은 ``blocked``로 반환합니다. 정상 선택은 검색 Result와 사용자 메시지를
        이전 OpenAI 응답에 연결하고, 같은 hotel_id의 취소 정책만 조회한 뒤 예약 초안
        형식의 최종 답변과 Trace를 반환합니다. 실제 예약은 실행하지 않습니다.
    """
    validation = validate_hotel_selection(state, actor, hotel_id)
    if not validation["valid"]:
        return {"status": "blocked", "reason": validation["reason"], "trace": state.trace}
    if not state.previous_response_id or not state.search_call_id:
        return {"status": "blocked", "reason": "MISSING_RESUME_STATE", "trace": state.trace}

    selected = validation["hotel"]
    state.selected_hotel_id = hotel_id
    state.status = "running"
    state.trace.append({"stage": "user_selection", "actor": actor, "hotel": selected})
    search_result = {
        "success": True,
        "items": state.hotel_candidates,
        "selected_hotel_id": hotel_id,
    }
    client = require_client()
    response = client.responses.create(
        model=MODEL,
        instructions=INSTRUCTIONS,
        previous_response_id=state.previous_response_id,
        input=[
            {
                "type": "function_call_output",
                "call_id": state.search_call_id,
                "output": json.dumps(search_result, ensure_ascii=False),
            },
            {"role": "user", "content": f"{hotel_id} 호텔을 선택했습니다. 취소 정책을 확인하고 예약 초안을 작성해 주세요."},
        ],
        tools=TOOLS,
        tool_choice="auto",
        parallel_tool_calls=False,
    )

    for step in range(1, max_steps + 1):
        calls = [item for item in response.output if item.type == "function_call"]
        if not calls:
            state.status = "completed"
            state.trace.append({"step": step, "stage": "model_final_answer", "text": response.output_text})
            return {
                "status": state.status,
                "selected_hotel": selected,
                "answer": response.output_text,
                "trace": state.trace,
            }

        call = calls[0]
        if call.name != "get_cancellation_policy":
            state.status = "blocked"
            return {"status": state.status, "reason": "TOOL_NOT_ALLOWED_AFTER_SELECTION", "trace": state.trace}
        arguments = parse_arguments(call)
        if arguments.get("hotel_id") != hotel_id:
            state.status = "blocked"
            return {"status": state.status, "reason": "SELECTED_HOTEL_CHANGED", "trace": state.trace}
        result = get_cancellation_policy(hotel_id)
        state.trace.append({"step": step, "stage": "tool_result", "tool": call.name, "result": result})
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


if __name__ == "__main__":
    agent_state = HotelSelectionState(
        run_id="hotel-selection-001",
        owner_id="user-01",
        question="부산에서 1박 15만 원 이하 호텔을 찾아 줘.",
    )
    paused = run_until_hotel_selection(agent_state)
    print("호텔 선택 대기:", json.dumps(paused, ensure_ascii=False, indent=2))
    if paused["status"] == "waiting_user":
        selected_id = input("hotel_id를 입력하세요: ").strip()
        completed = resume_after_hotel_selection(agent_state, "user-01", selected_id)
        print("선택 후 결과:", json.dumps(completed, ensure_ascii=False, indent=2))
