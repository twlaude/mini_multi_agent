"""여행 AI Agent의 조회, 초안 작성, 사용자 승인과 실행을 한 흐름으로 보여 줍니다.

상황:
사용자가 "제주 날씨에 맞는 여행 장소를 찾아 일정으로 저장해 줘"라고 요청합니다.
Agent는 날씨와 장소를 조회하고 일정 초안까지 자동으로 만들 수 있습니다. 그러나
일정 저장은 외부 상태를 변경하므로 바로 실행하지 않고 사용자에게 승인 여부를 묻습니다.

실행 흐름:
사용자 요청
→ 날씨 조회
→ 장소 검색
→ 여행 일정 초안 생성
→ 터미널에서 사용자에게 승인 여부 입력 요청
   ├─ y: 승인 대상을 확인하고 일정 저장
   └─ n: 아무것도 저장하지 않고 종료

이 파일은 승인 흐름 전체를 한눈에 보기 위한 단순한 Rule-based Agent 예제입니다.
다음 ``06_openai_safe_agent.py``에서는 다음 Tool을 고르는 부분을 LLM이 담당합니다.
"""

from dataclasses import dataclass
from typing import Any, Literal


Status = Literal["running", "waiting_approval", "completed", "rejected", "blocked"]


@dataclass
class AgentState:
    """승인 전후에 유지할 최소한의 여행 Agent State입니다."""

    run_id: str
    owner_id: str
    city: str
    weather: dict[str, Any] | None = None
    places: list[str] | None = None
    draft: dict[str, Any] | None = None
    status: Status = "running"


WEATHER = {"제주": {"condition": "비", "temperature_c": 21}}
PLACES = {"제주": ["비자림", "제주현대미술관"]}
PROCESSED_RUNS: set[str] = set()


def get_weather(city: str) -> dict[str, Any]:
    """여행 계획에 사용할 도시의 날씨를 조회합니다."""

    return {"city": city, **WEATHER.get(city, {"condition": "정보 없음"})}


def search_places(city: str) -> list[str]:
    """일정에 넣을 여행 장소 후보를 조회합니다."""

    return PLACES.get(city, [])


def save_itinerary(owner_id: str, draft: dict[str, Any]) -> dict[str, Any]:
    """사용자가 승인한 여행 일정이 저장됐다는 Mock Result를 반환합니다."""

    return {"owner_id": owner_id, "saved": True, "itinerary": draft}


def run_until_pause(state: AgentState) -> dict[str, Any]:
    """조회와 초안 작성을 진행하고 일정 저장 직전에 실행을 멈춥니다."""

    state.weather = get_weather(state.city)
    state.places = search_places(state.city)

    if not state.places:
        state.status = "blocked"
        return {"status": state.status, "reason": "NO_PLACES_FOUND"}

    state.draft = {
        "city": state.city,
        "place": state.places[0],
        "weather": state.weather["condition"],
    }
    state.status = "waiting_approval"
    return {
        "status": state.status,
        "question": "이 여행 일정을 저장할까요?",
        "approval_target": state.draft.copy(),
    }


def resume_after_approval(state: AgentState, decision: dict[str, Any]) -> dict[str, Any]:
    """사용자의 승인 또는 거부 결과에 따라 저장하거나 변경 없이 종료합니다."""

    if state.status != "waiting_approval":
        return {"status": "blocked", "reason": "NOT_WAITING_APPROVAL"}
    if decision.get("decision") == "reject":
        state.status = "rejected"
        return {"status": state.status, "reason": "USER_REJECTED"}
    if decision.get("decision") != "approve":
        return {"status": "blocked", "reason": "INVALID_DECISION"}
    if decision.get("actor") != state.owner_id:
        return {"status": "blocked", "reason": "INVALID_USER"}
    if decision.get("approval_target") != state.draft:
        return {"status": "blocked", "reason": "APPROVAL_TARGET_CHANGED"}
    if state.run_id in PROCESSED_RUNS:
        return {"status": "completed", "reason": "ALREADY_PROCESSED"}

    result = save_itinerary(state.owner_id, state.draft)
    PROCESSED_RUNS.add(state.run_id)
    state.status = "completed"
    return {"status": state.status, "result": result}


def ask_user_decision() -> str:
    """터미널에서 사용자가 y 또는 n을 입력할 때까지 승인 여부를 묻습니다."""

    while True:
        answer = input("일정을 저장할까요? [y/n]: ").strip().lower()
        if answer in {"y", "yes", "승인"}:
            return "approve"
        if answer in {"n", "no", "거절"}:
            return "reject"
        print("y(승인) 또는 n(거절)을 입력해 주세요.")


def main() -> None:
    """여행 초안을 보여 주고 사용자의 실제 입력으로 Agent 실행을 재개합니다."""

    state = AgentState(run_id="travel-001", owner_id="user-a", city="제주")
    paused = run_until_pause(state)

    if paused["status"] != "waiting_approval":
        print("일정을 만들 수 없습니다:", paused)
        return

    print("\n여행 일정 초안")
    print(paused["approval_target"])

    decision = {
        "decision": ask_user_decision(),
        "actor": state.owner_id,
        "approval_target": paused["approval_target"],
    }
    result = resume_after_approval(state, decision)

    if result["status"] == "completed":
        print("일정을 저장했습니다:", result["result"])
    elif result["status"] == "rejected":
        print("사용자가 거절하여 일정을 저장하지 않았습니다.")
    else:
        print("일정을 실행할 수 없습니다:", result)


if __name__ == "__main__":
    main()
