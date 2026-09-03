# 선택 학습: LangGraph Interrupt와 Resume

먼저 `02_pause_save_resume.py`에서 일반 Python으로 상태 저장과 재개를 이해합니다. 그다음 `01_interrupt_and_resume.py`에서 같은 개념을 LangGraph로 비교합니다.

| 직접 구현 | LangGraph |
| --- | --- |
| 저장된 Agent State | Checkpoint |
| `waiting_approval` 반환 | `interrupt()` |
| 저장 상태로 함수 재호출 | `Command(resume=...)` |
| `run_id` | `thread_id` |

```powershell
python .\10_optional_langgraph\01_interrupt_and_resume.py
```

LangGraph는 중단과 재개를 구현하지만 Tool Allowlist, 승인 대상 검증과 중복 실행 방지 정책을 대신하지 않습니다.
