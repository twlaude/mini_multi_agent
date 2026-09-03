"""일반 Python State로 Agent 실행의 중단, 저장과 재개를 구분합니다.

변경 직전의 실행 위치와 승인 대상을 State로 반환하고, 이후 구조화된 Command를 받아
같은 실행을 재개합니다. 실제 영구 저장소 없이 pause/resume에 필요한 최소 State 계약을
학습하기 위한 결정적 예제입니다.

여행 AI Agent에서는 언제 필요한가?
-------------------------------
사용자가 ``제주 여행 일정을 만들어 줘``라고 요청하면 Agent는 날씨와 장소를 조회하고
여행 일정 초안까지 자동으로 만들 수 있습니다. 조회와 초안 생성은 외부 상태를 바꾸지
않으므로 바로 실행해도 되지만, 일정을 캘린더에 저장하거나 호텔 예약 요청을 보내는
행동은 사용자의 데이터나 외부 시스템을 변경합니다.

이때 Agent 실행 흐름은 다음과 같습니다.

``사용자 요청 → 날씨·장소·호텔 조회 → 일정 또는 예약 초안 생성``
``→ 변경 대상 표시 → waiting_approval에서 중단 → State 저장``
``→ 사용자 승인·거절 → 같은 run_id와 State로 재개 → 변경 실행 또는 종료``

중단하는 이유는 Agent가 다음 행동을 몰라서가 아닙니다. 실행할 변경 내용은 이미
결정됐지만, 그 행동을 실제로 수행할 권한이 아직 없기 때문입니다. 따라서 이 상태는
호텔 후보를 골라 달라는 ``waiting_user``와 다릅니다. ``waiting_user``는 다음 판단에
필요한 정보가 부족한 상태이고, ``waiting_approval``은 변경 대상은 완성됐지만 사용자의
명시적인 실행 허가가 필요한 상태입니다.

이 파일의 ``draft``는 여행 일정 저장 또는 Mock 예약 요청을 단순화한 승인 Snapshot입니다.
``pause``는 Snapshot과 실행 위치를 저장하고, ``resume``은 승인 대기 상태·결정값·승인자를
검사한 뒤 완료 또는 거절 상태로 이동합니다. 실제 변경 Tool 실행과 승인 대상 재검증,
중복 실행 방지는 뒤의 ``04_safe_execution.py``와 ``05_complete_safe_agent.py``에서
단계적으로 추가합니다.
"""


ALLOWED_DECISIONS = {"approve", "reject"}


def pause(run_id: str, owner_id: str, draft: dict) -> dict:
    """변경 직전의 실행 정보를 승인 대기 State로 만듭니다.

    Args:
        run_id: 중단과 재개를 연결하는 실행 식별자입니다.
        owner_id: 승인할 수 있는 실행 소유자입니다.
        draft: 승인 화면에 표시하고 이후 다시 검증할 변경 초안입니다.

    Returns:
        현재 Node, 소유자, 초안과 ``waiting_approval`` 상태를 담은 dict입니다.
    """
    return {
        "run_id": run_id,
        "owner_id": owner_id,
        "status": "waiting_approval",
        "current_node": "approval",
        "draft": draft,
    }


def resume(saved_state: dict, command: dict) -> dict:
    """저장된 승인 대기 State를 구조화된 사용자 결정으로 재개합니다.

    승인 대기 상태, 허용된 decision과 실행 소유자를 다시 검사합니다. 검증을 통과하면
    ``completed`` 또는 ``rejected``로 이동하며, 이 함수 자체는 외부 변경을 실행하지
    않고 상태 전이만 보여줍니다.
    """
    if saved_state["status"] != "waiting_approval":
        raise ValueError("승인 대기 상태만 재개할 수 있습니다.")
    if command.get("decision") not in ALLOWED_DECISIONS:
        raise ValueError("decision은 approve 또는 reject여야 합니다.")
    if command.get("actor") != saved_state["owner_id"]:
        raise ValueError("실행 소유자만 결정할 수 있습니다.")
    approved = command["decision"] == "approve"
    return {
        **saved_state,
        "status": "completed" if approved else "rejected",
        "current_node": "end",
        "decision": command["decision"],
        "decision_actor": command["actor"],
    }


if __name__ == "__main__":
    saved = pause("run-001", "user-a", {"action": "create_mock_reservation"})
    print("저장된 상태:", saved)
    print("승인 재개:", resume(saved, {"decision": "approve", "actor": "user-a"}))
    print("거절 재개:", resume(saved, {"decision": "reject", "actor": "user-a"}))
