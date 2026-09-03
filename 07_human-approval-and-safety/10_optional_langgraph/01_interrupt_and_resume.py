"""선택 학습: LangGraph interrupt와 구조화된 Command(resume=...) 예제."""

from operator import add
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class ApprovalState(TypedDict, total=False):
    """LangGraph Node 사이에서 공유하고 Checkpoint에 저장할 승인 State 계약입니다."""
    owner_id: str
    reservation: dict
    decision: str
    decision_actor: str
    status: str
    result: str
    trace: Annotated[list[str], add]


def prepare(state: ApprovalState) -> dict:
    """Graph 실행을 승인 대기 상태로 전환하고 준비 Trace를 추가합니다."""
    return {"status": "waiting_approval", "trace": ["prepare"]}


def request_approval(state: ApprovalState) -> dict:
    """구조화된 승인 질문으로 Graph를 중단하고 Command 입력을 검증합니다.

    ``interrupt``가 반환한 값도 외부 입력이므로 decision과 actor를 다시 검사합니다.
    LangGraph Checkpoint는 State를 복원하지만 사용자 인증과 권한 검사를 대신하지 않습니다.
    """
    response = interrupt(
        {
            "question": "이 Mock 예약 요청을 승인하시겠습니까?",
            "reservation": state["reservation"],
            "allowed_actions": ["approve", "reject"],
        }
    )
    if not isinstance(response, dict) or response.get("decision") not in {"approve", "reject"}:
        raise ValueError("올바른 승인 결정이 아닙니다.")
    if response.get("actor") != state["owner_id"]:
        raise ValueError("실행 소유자만 결정할 수 있습니다.")
    return {
        "decision": response["decision"],
        "decision_actor": response["actor"],
        "trace": ["approval"],
    }


def execute_mock(state: ApprovalState) -> dict:
    """검증된 승인 또는 거절 결정에 따라 Mock 변경 단계와 종료 상태를 반환합니다."""
    if state["decision"] == "reject":
        return {"status": "rejected", "result": "사용자가 요청을 거절했습니다.", "trace": ["reject"]}
    return {"status": "completed", "result": "Mock 예약 요청이 한 번 기록되었습니다.", "trace": ["execute_mock"]}


builder = StateGraph(ApprovalState)
builder.add_node("prepare", prepare)
builder.add_node("request_approval", request_approval)
builder.add_node("execute_mock", execute_mock)
builder.add_edge(START, "prepare")
builder.add_edge("prepare", "request_approval")
builder.add_edge("request_approval", "execute_mock")
builder.add_edge("execute_mock", END)
graph = builder.compile(checkpointer=InMemorySaver())


if __name__ == "__main__":
    config = {"configurable": {"thread_id": "approval-demo-001"}}
    initial: ApprovalState = {
        "owner_id": "user-a",
        "reservation": {"hotel": "바다 호텔", "guests": 2},
        "trace": [],
    }
    paused = graph.invoke(initial, config=config)
    print("중단 정보:", paused.get("__interrupt__"))
    resumed = graph.invoke(
        Command(resume={"decision": "approve", "actor": "user-a", "note": "확인"}),
        config=config,
    )
    print("재개 결과:", resumed)
