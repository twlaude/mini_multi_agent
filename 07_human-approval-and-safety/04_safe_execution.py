"""여행 AI Agent에서 승인된 변경 요청의 중복 실행을 방지합니다.

이 예제는 Agent가 여행 일정이나 예약 초안을 만든 뒤 사용자가 실행을 승인한
상황을 가정합니다. 사용자가 승인 버튼을 두 번 클릭하거나 네트워크 재시도로
같은 요청이 다시 전달되더라도 실제 변경 작업은 한 번만 실행되어야 합니다.

실행 흐름:
여행 일정 초안 생성
→ 사용자 승인
→ run_id 중복 여부 확인
→ 처음 받은 요청이면 변경 Tool 실행
→ 같은 run_id가 다시 들어오면 already_processed 반환

이를 멱등성(Idempotency)이라고 합니다. 실제 서비스에서는 메모리 set 대신
Database Unique Constraint, Idempotency Key와 Transaction 등을 사용합니다.
"""


PROCESSED_RUNS: set[str] = set()
AUDIT_LOG: list[dict] = []


def execute_once(run_id: str, owner_id: str, decision: dict) -> dict:
    """승인된 Mock 변경을 동일 run_id에서 한 번만 실행합니다.

    Args:
        run_id: 중복 실행 여부를 판정하는 교육용 Idempotency Key입니다.
        owner_id: 변경 실행의 소유자입니다.
        decision: 구조화된 decision과 actor를 포함한 승인 결과입니다.

    Returns:
        승인 실패, 이미 처리됨 또는 완료 상태를 반환합니다. 메모리 set과
        Audit Log는 개념 확인용이며 프로세스 재시작과 동시 Transaction을 보장하지 않습니다.
    """
    if decision.get("actor") != owner_id:
        return {"status": "blocked", "reason": "실행 소유자가 아님"}
    if decision.get("decision") != "approve":
        return {"status": "rejected", "reason": "승인되지 않음"}
    if run_id in PROCESSED_RUNS:
        return {"status": "already_processed", "run_id": run_id}

    # 학습용 Mock에서는 처리 표시 후 실패가 없다고 가정합니다.
    PROCESSED_RUNS.add(run_id)
    event = {"run_id": run_id, "actor": decision["actor"], "action": "create_mock_reservation"}
    AUDIT_LOG.append(event)
    return {"status": "completed", "event": event}


if __name__ == "__main__":
    approved = {"decision": "approve", "actor": "user-a"}
    print("첫 실행:", execute_once("run-001", "user-a", approved))
    print("중복 실행:", execute_once("run-001", "user-a", approved))
    print("감사 로그:", AUDIT_LOG)
