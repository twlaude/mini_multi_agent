"""승인, 거절과 잘못된 사용자 결정을 하나의 구조화된 계약으로 검증합니다.

자연어의 긍정 표현을 추측하지 않고 ``decision``과 ``actor`` 필드를 요구합니다. 승인과
거절을 같은 입력 Schema로 처리하여 재개 Workflow가 예측 가능한 상태를 받게 합니다.

여행 AI Agent에서는 어떤 상황인가?
----------------------------
앞의 ``02_pause_save_resume.py``에서 Agent는 제주 여행 일정 또는 호텔 예약 초안을
만든 뒤 ``waiting_approval`` 상태로 멈췄습니다. 사용자는 승인 화면에서 저장할 내용을
확인한 다음 승인하거나 거절합니다. 이때 ``좋아요``, ``진행해`` 같은 자연어를 Backend가
자의적으로 승인으로 해석하면 의도하지 않은 변경이 실행될 수 있습니다.

전체 흐름에서 이 파일의 위치는 다음과 같습니다.

``여행 초안 생성 → 승인 대기 → 사용자 결정 Payload 수신``
``→ decision·actor 검증 → approve면 재개 / reject면 종료 / 잘못된 값이면 차단``

예를 들어 사용자가 자신의 제주 일정 저장 요청을 승인하면
``{"decision": "approve", "actor": "user-a"}``처럼 구조화된 Payload가 전달됩니다.
다른 사용자가 승인하거나 ``decision="edit"``처럼 허용되지 않은 값이 오면 변경 단계로
넘어가지 않습니다. 이 파일은 아직 여행 일정을 실제로 저장하지 않고, 다음 단계가
신뢰할 수 있는 승인 결과만 받도록 사용자 결정의 입구를 검증합니다.
"""


def validate_decision(payload: object, owner_id: str) -> dict:
    """승인 Payload의 구조, 결정값과 승인자를 검증합니다.

    Args:
        payload: 외부에서 받은 비신뢰 승인 또는 거절 Payload입니다.
        owner_id: 해당 실행을 승인할 수 있는 소유자 식별자입니다.

    Returns:
        검증 성공 시 정규화된 decision과 actor를, 실패 시 ``valid=False``와 이유를
        반환합니다. 문자열 ``"approve"``만 전달하는 입력은 허용하지 않습니다.
    """
    if not isinstance(payload, dict):
        return {"valid": False, "reason": "결정은 dict여야 합니다."}
    if payload.get("decision") not in {"approve", "reject"}:
        return {"valid": False, "reason": "허용되지 않은 decision"}
    if payload.get("actor") != owner_id:
        return {"valid": False, "reason": "실행 소유자가 아님"}
    return {"valid": True, "decision": payload["decision"], "actor": payload["actor"]}


if __name__ == "__main__":
    cases = [
        {"decision": "approve", "actor": "user-a"},
        {"decision": "reject", "actor": "user-a"},
        {"decision": "edit", "actor": "user-a"},
        {"decision": "approve", "actor": "user-b"},
        "approve",
    ]
    for case in cases:
        print(case, "→", validate_decision(case, owner_id="user-a"))
