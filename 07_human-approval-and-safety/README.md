# 07 Human Approval and Safety

좋은 AI Agent는 모든 행동을 바로 실행하지 않습니다. 읽기와 초안 작성은 자동으로 진행하되, 외부 상태를 바꾸는 행동은 실행 직전에 멈추고 사용자에게 구체적인 승인을 받습니다.

이 장은 복잡한 권한 시스템이나 다른 사용자 자원의 소유권 검사가 아니라, **현재 사용자가 요청한 작업을 Agent가 진행하다가 실제 변경 전에 중단하고 승인 또는 거부에 따라 재개하는 과정**에 집중합니다.

```text
사용자 요청
→ Agent가 읽기 Tool 실행 및 초안 작성
→ 변경 Tool 제안
→ State 저장 + 실행 중단
→ 사용자 승인 또는 거부
   ├─ 승인 → 승인 대상을 재검사하고 한 번만 실행
   └─ 거부 → 변경 없이 종료
```

## 1. 왜 승인이 필요한가?

LLM은 다음 행동을 제안할 수 있지만 실제 실행 권한을 갖는 것은 아닙니다. 애플리케이션 코드가 Tool의 위험도를 확인하고 실행 여부를 결정해야 합니다.

```text
날씨 조회
→ read
→ 승인 없이 자동 실행

여행 일정 초안 작성
→ draft
→ 외부 상태를 바꾸지 않으므로 자동 실행

캘린더에 일정 저장
→ change
→ 사용자 승인 이후 실행

허용하지 않은 고위험 작업
→ forbidden
→ 승인 여부와 관계없이 실행 차단
```

| 위험도 | 의미 | 처리 |
| --- | --- | --- |
| `read` | 데이터를 조회합니다. | 자동 실행 |
| `draft` | 외부 변경 없이 결과를 준비합니다. | 자동 실행 |
| `change` | 일정 저장처럼 외부 상태를 변경합니다. | 사용자 승인 후 실행 |
| `forbidden` | 현재 Agent에 허용하지 않은 작업입니다. | 실행 차단 |

Tool Allowlist도 필요합니다. 다만 별도의 소유권 예제로 분리하지 않고 Agent가 호출 가능한 Tool과 각 Tool의 위험도를 정하는 기본 정책으로 사용합니다.

## 2. 사용자 질문과 승인은 다르다

```text
waiting_user
└─ 도시, 날짜, 호텔처럼 작업에 필요한 정보가 부족하다.

waiting_approval
└─ 실행 정보는 충분하지만 외부 변경에 대한 동의가 필요하다.
```

호텔 후보 중 하나를 고르는 것은 정보 보완입니다. 반면 선택한 일정을 실제 캘린더나 저장소에 기록하는 것은 외부 변경이므로 승인이 필요합니다.

## 3. 승인 대상은 구체적이어야 한다

사용자가 단순히 `예`라고 답했다는 사실만 저장하면 안 됩니다. 무엇을 승인했는지 함께 보관해야 합니다.

```python
{
    "decision": "approve",
    "approval_target": {
        "city": "제주",
        "place": "비자림",
        "date": "2026-09-10"
    }
}
```

승인 후 실행할 내용이 Snapshot과 달라졌다면 다시 승인받아야 합니다. 운영 환경에서는 승인 응답을 보낸 사람이 현재 로그인한 사용자인지도 세션이나 검증된 토큰으로 확인합니다. 이는 일반적인 인증 처리이며, 이 장에서는 다른 사용자의 자원을 승인하는 별도 시나리오로 확장하지 않습니다.

## 4. 중단·저장·재개

```text
조회 Tool
→ 초안 생성
→ waiting_approval
→ State 저장
→ 사용자 결정
→ 같은 run_id와 State로 재개
→ 승인 대상 재검사
→ 변경 Tool 실행
```

State에는 실행을 구분하는 `run_id`, Tool Result, 초안, 현재 상태, 승인 대상과 Trace를 보관합니다.

## 5. 승인 후에도 검사해야 하는 것

1. Agent가 실제로 `waiting_approval` 상태인가?
2. 결정값이 `approve` 또는 `reject`인가?
3. 승인한 대상과 지금 실행할 대상이 같은가?
4. 같은 `run_id`가 이미 실행되지 않았는가?

동일 요청이 재전송되더라도 변경 Tool은 한 번만 실행되어야 합니다. 예제에서는 메모리 `set`으로 보여 주며, 운영 환경에서는 Database의 Unique Constraint와 Transaction 등을 사용합니다.

## 6. 전체 Agent 흐름

```text
LLM 또는 규칙이 다음 행동 선택
   ↓
Tool 정책에서 위험도 확인
   ├─ read / draft → 실행하고 결과를 State에 저장
   ├─ change       → 실행하지 않고 승인 요청
   └─ forbidden    → 차단
                         ↓
                   사용자 결정
                         ↓
             상태·결정값·승인 대상 재검사
                         ↓
                 중복 실행 여부 검사
                         ↓
                    변경 Tool 실행
                         ↓
                 Result·Trace·Audit 저장
```

규칙 기반 예제에서는 Python 함수가 다음 행동을 선택합니다. OpenAI 예제에서는 LLM이 Tool을 선택하지만 승인과 실제 Tool 실행 여부는 여전히 Python 코드가 통제합니다.

## 7. 예제 순서

| 순서 | 파일 | 핵심 내용 |
| ---: | --- | --- |
| 7-0 | `00_agent_design_and_boundaries.md` | Single/Multi-Agent와 실행 경계 참고 설명 |
| 7-1 | `01_action_risk.py` | 읽기·초안·변경·금지 작업 분류 |
| 7-2 | `02_pause_save_resume.py` | 일반 Python으로 중단·상태 저장·재개 |
| 7-3 | `03_approve_and_reject.py` | 사용자의 승인·거부와 잘못된 결정 검증 |
| 7-4 | `04_safe_execution.py` | 승인된 변경의 단일 실행과 중복 방지 |
| 7-5 | `05_complete_safe_agent.py` | 조회부터 승인·Audit까지 전체 흐름 통합 |
| 7-6 | `06_openai_safe_agent.py` | OpenAI Tool Calling과 승인 후 Agent Loop 재개 |
| 7-7 | `07_openai_hotel_selection.py` | 정보 보완과 승인을 구분하는 호텔 선택 예제 |
| 7-8 | `08_two_stage_approval.py` | 일정 저장과 호텔 예약을 분리한 2단계 승인 및 SQLite 저장 |
| 선택 | `10_optional_langgraph` | 같은 중단·재개를 LangGraph로 표현 |

기존 소유권 검사와 Prompt Injection 경계 파일은 핵심 승인 흐름에서 제거했습니다. 이런 정책은 다중 사용자 서비스나 운영 보안을 설계할 때 추가할 수 있지만 현재 단계에서는 승인 Loop에 필요한 내용만 다룹니다.

## 8. 실행

```powershell
cd C:\aidevs\05_llm-agent-orchestration\07_human-approval-and-safety
python .\01_action_risk.py
python .\02_pause_save_resume.py
python .\03_approve_and_reject.py
python .\04_safe_execution.py
python .\05_complete_safe_agent.py
python .\08_two_stage_approval.py
```

실제 OpenAI Model이 Tool을 선택하는 예제는 과정 루트 `.env`에 `OPENAI_API_KEY`를 설정한 뒤 실행합니다.

```powershell
cd C:\aidevs\05_llm-agent-orchestration
python .\07_human-approval-and-safety\06_openai_safe_agent.py
python .\07_human-approval-and-safety\07_openai_hotel_selection.py
```

`06`과 `07`은 실제 예약이나 결제를 실행하지 않고 Mock Result만 만듭니다. 별도의
OpenAI API Key가 필요하지 않은 `08`은
1차 승인 후 여행 일정을 SQLite에 저장하고, 2차 승인 후 Mock 호텔 예약 결과를 같은
Database에 기록합니다. 외부 호텔 예약이나 결제 API는 호출하지 않습니다.

## 9. 테스트

```powershell
cd C:\aidevs\05_llm-agent-orchestration
pytest -q .\07_human-approval-and-safety\tests
```

테스트는 검색 결과 없음, 승인 대상 변경, 사용자 거부, 잘못된 호텔 선택과 중복 실행 방지를 확인합니다.

## 10. 선택 학습: LangGraph

먼저 `02_pause_save_resume.py`에서 일반 Python의 중단·저장·재개를 이해합니다. 이후 `10_optional_langgraph`에서 같은 개념을 Checkpoint, `interrupt()`와 `Command(resume=...)`로 비교합니다.

LangGraph는 State와 중단·재개를 표현하는 선택 Framework입니다. 승인 정책 자체를 대신하지 않으므로 작은 예제에서는 순수 Python만으로도 충분합니다.

## 핵심 정리

```text
LLM
= 다음 행동과 Tool Call을 제안한다.

Backend 정책
= Tool의 위험도와 실행 가능 여부를 결정한다.

Human Approval
= 구체적인 외부 변경을 실행해도 되는지 사용자가 결정한다.

Agent State
= 승인 전까지의 결과와 승인 대상을 저장하고 실행을 재개한다.
```

이 장의 학습 목표는 복잡한 권한 시스템을 만드는 것이 아니라, **AI Agent가 외부 변경 직전에 멈추고 사용자의 결정에 따라 안전하게 이어서 실행되는 구조**를 이해하는 것입니다.
