# AI Agent 경계와 Single·Multi-Agent 설계 가이드

Tool을 여러 개 사용하는 복잡한 AI Agent와 Multi-Agent 시스템은 겉으로 비슷해 보입니다. 하지만 둘을 나누는 기준은 **Tool이나 실행 단계의 개수가 아니라 독립적으로 판단하는 주체의 개수**입니다.

```text
Tool을 10개 사용해도 판단 주체가 하나면 Single Agent
Tool이 2개뿐이어도 독립적인 판단 주체가 여러 개면 Multi-Agent
```

이 문서는 AI Agent의 역할과 권한 경계를 정하고 다음 질문에 답하기 위한 설계 가이드입니다.

- Tool, Workflow와 Agent는 어떻게 구분하는가?
- Tool을 여러 개 사용하는 Single Agent란 무엇인가?
- 언제 하나의 Agent로 만드는 것이 좋은가?
- 언제 여러 Agent를 오케스트레이션하는 것이 좋은가?
- Multi-Agent처럼 보이지만 실제로는 아닌 구조는 무엇인가?
- 실무에서 Multi-Agent를 도입할 때 어떤 근거가 필요한가?
- Agent마다 어떤 Tool, 데이터와 변경 권한을 허용해야 하는가?

## 1. 가장 먼저 구분할 네 가지

### Tool

Tool은 판단하는 주체가 아니라 한 가지 작업을 수행하는 기능입니다.

```python
get_weather(city)
search_attractions(city)
add_to_itinerary(place)
```

Tool의 일반적인 특징은 다음과 같습니다.

- 입력과 출력 계약이 명확합니다.
- 한 가지 책임을 수행합니다.
- 사용자 목표를 스스로 만들지 않습니다.
- 다른 Tool을 선택하지 않습니다.
- 실행 결과만 반환합니다.
- Backend가 허용한 범위 안에서만 실행됩니다.

날씨 조회, 문서 검색, SQL 조회, 이메일 초안 저장과 일정 등록 등이 Tool에 해당합니다.

### Workflow

Workflow는 개발자가 미리 정한 단계와 규칙에 따라 Tool이나 함수를 실행합니다.

```text
입력 검증 → 회원 조회 → 재고 조회 → 예약 가능 여부 검사 → 결과 반환
```

조건 분기가 있어도 다음 경로가 명시적인 코드나 업무 규칙으로 결정된다면 Workflow입니다.

```text
결제 금액이 100만 원 이상인가?
├─ 예     → 관리자 승인
└─ 아니오 → 자동 처리
```

Workflow의 핵심은 **동일한 상태와 입력에는 동일한 경로와 결과가 필요하다**는 것입니다.

### Single Agent

Single Agent는 하나의 Model 또는 하나의 Agent Loop가 현재 목표와 State를 보고 다음 행동을 결정합니다.

```text
사용자
   ↓
Travel Agent
   ├─ 날씨 Tool
   ├─ 관광지 Tool
   ├─ 호텔 Tool
   ├─ 일정 Tool
   └─ 사용자에게 재질문
```

Tool이 여러 개여도 다음 행동을 결정하는 주체는 `Travel Agent` 하나입니다.

```text
하나의 목표
하나의 주요 판단 Context
하나의 Agent State
하나의 다음 행동 결정 Loop
여러 개의 Tool
```

`10_labs/08_multi_tool_user_resume.py`도 Single Agent 예제입니다.

```text
Tool 1 실행 → Tool 2 실행 → 사용자 질문
→ 기존 State로 재개 → Tool 3 실행 → 종료
```

실행이 여러 단계이고 Tool이 세 개이지만 판단 흐름과 상태를 소유하는 Agent는 하나입니다.

### Multi-Agent

Multi-Agent는 역할, 목표, 판단 기준, Context 또는 권한이 다른 Agent가 여러 개 존재하는 구조입니다.

```text
사용자 요청
   ↓
Coordinator Agent
   ├─ Weather Agent
   │    └─ 날씨 Tool
   ├─ Travel Research Agent
   │    └─ 관광지·호텔 검색 Tool
   └─ Schedule Agent
        └─ 일정 조회·등록 Tool
```

각 Agent는 단순 함수가 아니라 자신의 판단 과정과 제한된 실행 범위를 가집니다.

```text
Weather Agent
- 날씨 분석 목표와 전용 지침
- 날씨 관련 Context와 Tool
- 분석 완료 조건

Schedule Agent
- 일정 구성 목표와 전용 지침
- 캘린더 Context와 Tool
- 일정 충돌 해결 기준과 완료 조건
```

## 2. 무엇이 Agent의 경계인가

Agent를 나눌 때는 이름이나 파일 경계가 아니라 다음 요소를 확인합니다.

| 경계 | 확인할 질문 |
| --- | --- |
| Goal | 서로 독립적으로 달성하거나 평가할 수 있는 목표인가? |
| Decision | 각 역할이 다음 행동을 별도로 판단하는가? |
| Context | 서로 다른 정보와 대화 기록이 필요한가? |
| Tool | 역할마다 사용하는 Tool 집합이 크게 다른가? |
| Permission | 역할마다 접근 권한을 격리해야 하는가? |
| State | 독립적으로 유지하거나 재개해야 하는 상태가 있는가? |
| Completion | 역할마다 완료 조건과 실패 조건이 다른가? |
| Evaluation | 역할별 품질 기준을 별도로 측정할 수 있는가? |

이 중 여러 경계가 실제로 존재하면 Agent 분리를 고려할 수 있습니다. 반대로 공통 목표와 State에서 고정된 함수만 실행한다면 하나의 Agent 내부 단계나 Tool일 가능성이 큽니다.

## 3. Multi-Agent처럼 보이지만 아닌 구조

### Node가 여러 개인 Graph

```text
Planner Node → Tool Node → Validation Node → Answer Node
```

LangGraph Node가 여러 개라고 Multi-Agent가 되지는 않습니다. 하나의 공통 목표와 State를 처리하는 단계라면 하나의 Agent Workflow입니다.

### 역할 이름이 붙은 함수

```text
SearchAgent
ValidationAgent
FormatterAgent
```

이름에 `Agent`가 있어도 정해진 함수만 실행하고 다음 행동을 판단하지 않는다면 실제로는 검색 함수, 검증 함수 또는 포맷 함수입니다.

### LLM을 호출하는 모든 단계

LLM을 호출한다고 모두 Agent인 것도 아닙니다.

```text
문서 요약 LLM
문의 유형 분류 LLM
arguments 추출 LLM
```

정해진 입력을 한 번 변환하고 종료한다면 `LLM Node`, `Classifier` 또는 `Worker`라고 부르는 편이 정확합니다.

### Tool을 여러 개 호출하는 Workflow

```text
항상 날씨 조회 → 항상 관광지 검색 → 항상 결과 요약
```

Tool이 세 개 이상이어도 순서가 고정되어 있다면 Agent가 아니라 Tool을 사용하는 Workflow입니다.

## 4. 기본 선택은 Single Agent

처음에는 다음 구조로 시작하는 것이 좋습니다.

```text
하나의 Agent
+ 명확하게 분리된 Tool
+ 결정적인 Backend Workflow
+ 필요한 사용자 승인
```

Single Agent의 장점은 다음과 같습니다.

- 구현과 디버깅이 쉽습니다.
- 전체 Context를 한곳에서 관리할 수 있습니다.
- Model 호출 횟수와 비용이 비교적 적습니다.
- 실행 경로와 실패 원인을 추적하기 쉽습니다.
- Agent 사이의 결과 충돌과 책임 전가가 없습니다.
- 테스트해야 할 Agent 조합이 적습니다.
- 사용자 대화의 일관성을 유지하기 쉽습니다.

다음 조건에서는 Single Agent가 적합합니다.

- 하나의 사용자 목표를 처리합니다.
- 사용하는 Tool들이 서로 밀접하게 연관되어 있습니다.
- 하나의 System Prompt와 Context로 판단할 수 있습니다.
- 작업이 대부분 순차적으로 실행됩니다.
- 역할별 권한 격리가 필요하지 않습니다.
- 하나의 State로 실행을 설명하고 재개할 수 있습니다.
- Agent를 나눠도 독립적인 평가 기준을 만들기 어렵습니다.

예를 들어 일반적인 여행 도우미는 하나의 Agent로 충분합니다.

```text
Travel Agent
├─ 날씨 조회
├─ 관광지 검색
├─ 호텔 검색
├─ 사용자 재질문
└─ 일정 등록
```

Tool이 다섯 개라는 이유만으로 Agent를 다섯 개로 나누지 않습니다.

## 5. Multi-Agent를 고려할 구체적인 근거

Multi-Agent는 더 발전된 구조라서 선택하는 것이 아닙니다. Single Agent에서 측정 가능한 문제가 발생했고, 역할 분리가 그 문제를 해결할 때 선택합니다.

### 서로 다른 전문 지식과 지침이 필요한 경우

```text
법률 검토 Agent
기술 검토 Agent
재무 검토 Agent
```

각 분야의 판단 기준과 참고 문서가 크게 다르면 하나의 Prompt에 모든 규칙을 넣었을 때 지시가 충돌하거나 중요한 규칙이 희석될 수 있습니다.

분리 근거:

- 사용하는 전문 용어와 문서가 다릅니다.
- 결과를 평가하는 기준이 다릅니다.
- 각 역할이 독립적인 수정 의견을 낼 수 있습니다.

### Context를 분리해야 하는 경우

```text
고객 상담 Agent
내부 보안 분석 Agent
관리자 운영 Agent
```

모든 Agent가 모든 Context를 볼 필요가 없으며, 오히려 보면 안 되는 경우도 있습니다.

- 개인정보와 내부 운영 정보를 격리해야 합니다.
- 분야별 문서가 너무 커서 하나의 Context에 넣기 어렵습니다.
- Agent별로 필요한 기억과 대화 기록이 다릅니다.

### Tool과 권한을 역할별로 격리해야 하는 경우

```text
Research Agent
└─ 읽기 전용 검색 Tool

Execution Agent
└─ 등록·변경 Tool

Backend Policy
└─ 실행 권한과 사용자 승인 검증
```

조회 역할과 변경 역할을 분리하면 실수로 상태 변경 Tool을 선택할 가능성을 줄일 수 있습니다. 하지만 보안 승인을 LLM Agent의 판단에만 맡기면 안 됩니다. 최종 권한 검사는 Backend가 수행해야 합니다.

### 독립적인 작업을 병렬 처리할 수 있는 경우

```text
시장 조사 Agent ─────┐
기술 조사 Agent ─────┼─→ 결과 종합 Agent
경쟁사 조사 Agent ───┘
```

서로 의존하지 않는 조사를 동시에 실행하면 전체 시간을 줄일 수 있습니다.

- 각 작업의 입력과 출력 계약이 명확합니다.
- 한 작업의 중간 결과가 다른 작업에 필요하지 않습니다.
- 각각 실패하거나 재시도해도 다른 작업에 영향을 주지 않습니다.

### 작성과 검토의 평가 기준이 다른 경우

```text
작성 Agent → 검토 Agent → 수정 요청 → 작성 Agent
```

작성과 검토의 목표가 명확히 다르고 검토 기준이 구체적일 때 유용합니다.

```text
작성 Agent 목표: 요구사항을 만족하는 초안을 만든다.
검토 Agent 목표: 사실성, 누락, 형식과 정책 위반을 검사한다.
```

단순히 Reviewer라는 이름을 추가한다고 품질이 자동으로 좋아지지는 않습니다. 검토 Checklist와 통과 조건이 필요합니다.

### 하나의 Agent Context가 지나치게 복잡한 경우

한 Agent가 모든 문서, Tool Schema, 업무 규칙과 이전 결과를 받으면 중요한 지시를 놓치거나 불필요한 Tool을 선택할 수 있습니다. 분야별 Agent가 필요한 Context만 읽고 구조화된 결과만 Coordinator에게 전달하도록 나눌 수 있습니다.

## 6. Agent를 나누지 말아야 하는 신호

다음 이유만으로 Multi-Agent를 선택하면 복잡성만 늘어날 가능성이 높습니다.

- Tool이 많습니다.
- 처리 단계가 많습니다.
- LangGraph Node가 많습니다.
- 현실 조직에 부서가 여러 개 있습니다.
- 역할 이름을 여러 개 만들 수 있습니다.
- Multi-Agent가 더 고급 기술처럼 보입니다.
- Model을 여러 번 호출하면 품질이 좋아질 것 같습니다.

다음처럼 설명할 수 있는 구성 요소는 대개 Agent가 아니라 Tool이나 Workflow 단계면 충분합니다.

```text
입력이 들어오면 항상 같은 한 가지 작업을 수행한다.
다음 행동에 대한 판단 없이 결과만 반환한다.
별도의 목표, State와 종료 조건이 없다.
```

## 7. Single Agent와 Multi-Agent 비교

| 기준 | Single Agent | Multi-Agent |
| --- | --- | --- |
| 판단 주체 | 하나 | 여러 개 |
| 목표 | 하나의 공통 목표 | 역할별 하위 목표 |
| Context | 대부분 공유 | 역할별로 분리 가능 |
| Tool | 한 Agent가 여러 Tool 사용 | Agent별 Tool 집합 제한 가능 |
| State | 하나의 주요 State | Agent별 State와 공유 State |
| Model 호출 | 상대적으로 적음 | Agent 협업만큼 증가 |
| 실행 추적 | 비교적 단순 | 전달·충돌·재시도까지 추적 필요 |
| 테스트 | 입력별 Agent 행동 평가 | Agent별 평가 + 협업 조합 평가 |
| 적합한 문제 | 하나의 역할로 해결 가능한 목표 | 전문성·권한·Context 경계가 명확한 목표 |
| 기본 선택 | 우선 고려 | 근거가 있을 때 도입 |

## 8. 실무 판단 Checklist

### Single Agent를 유지할 근거

- [ ] 전체 요청을 하나의 사용자 목표로 설명할 수 있는가?
- [ ] 하나의 Prompt와 Context로 판단 가능한가?
- [ ] 하나의 State로 실행을 설명할 수 있는가?
- [ ] Tool들이 같은 업무 영역에 속하는가?
- [ ] 역할별 권한 격리가 필요하지 않은가?
- [ ] 작업이 주로 순차적으로 실행되는가?
- [ ] Single Agent의 품질, 비용과 지연이 허용 범위인가?

대부분 `예`라면 Single Agent를 유지합니다.

### Multi-Agent를 검토할 근거

- [ ] 역할마다 전문 지침과 참고 문서가 크게 다른가?
- [ ] Agent마다 독립적인 목표와 완료 조건이 있는가?
- [ ] 역할별 Tool 또는 데이터 권한을 격리해야 하는가?
- [ ] 작업들을 독립적으로 병렬 처리할 수 있는가?
- [ ] 작성과 검토처럼 결과 평가 기준이 다른가?
- [ ] 하나의 Context가 너무 커서 판단 품질이 떨어졌는가?
- [ ] Agent 분리 후 품질 향상을 측정할 평가 방법이 있는가?
- [ ] 증가하는 비용, 지연과 운영 복잡성을 감당할 수 있는가?

한두 항목만 해당한다면 함수, Tool 또는 Node 분리로 충분한지 먼저 확인합니다.

## 9. 권장 설계 순서

처음부터 Multi-Agent로 설계하지 않고 복잡성이 생긴 지점에서 단계적으로 확장합니다.

```text
1. 일반 Python 함수
   ↓
2. 외부 기능을 Tool로 분리
   ↓
3. 순서가 고정되어 있으면 Workflow
   ↓
4. 실행 중 다음 행동을 선택해야 하면 Single Agent
   ↓
5. Single Agent의 한계를 평가로 확인
   ↓
6. 필요한 역할만 별도 Agent로 분리
   ↓
7. Coordinator 또는 Workflow로 오케스트레이션
```

Multi-Agent는 Single Agent의 상위 단계가 아니라 **Single Agent의 명확한 한계를 해결하기 위한 분산 설계**입니다.

## 10. Multi-Agent 오케스트레이션 패턴

여러 Agent를 연결할 때는 Agent끼리 자유롭게 대화하게 하기보다 입력, 출력, 반복 횟수와 종료 조건을 통제하는 것이 좋습니다.

### Coordinator 패턴

```text
사용자
   ↓
Coordinator Agent
   ├─ Research Agent
   ├─ Analysis Agent
   └─ Writing Agent
```

Coordinator가 요청을 분해하고 적절한 Agent에게 작업을 배정한 뒤 결과를 종합합니다. 일반적으로 가장 이해하기 쉬운 Multi-Agent 구조입니다.

- Coordinator가 각 Agent의 입력을 명확히 만들어야 합니다.
- Worker 결과는 자연어만이 아니라 구조화된 Schema로 받는 것이 좋습니다.
- 어떤 Worker가 실패했는지 Trace에 남겨야 합니다.

### 고정 Pipeline 패턴

```text
Research Agent → Draft Agent → Review Agent → 최종 결과
```

순서가 명확한 문서 작성, 코드 생성과 검토 업무에 적합합니다. 여러 Agent가 있지만 Workflow가 실행 순서를 통제하므로 `Multi-Agent Workflow`라고 볼 수 있습니다.

### Supervisor 반복 패턴

```text
Worker Agent
    ↓
Supervisor Agent
    ├─ 통과 → 종료
    └─ 수정 요청 → Worker Agent
```

검토 기준을 만족할 때까지 제한된 횟수로 반복합니다. 최대 수정 횟수, 명시적인 통과 기준, 실패 종료 이유와 같은 피드백의 무한 반복 방지가 필요합니다.

### 병렬 Worker 패턴

```text
             ┌→ Worker A ─┐
Coordinator ─┼→ Worker B ─┼→ 결과 종합
             └→ Worker C ─┘
```

독립적인 조사와 분석에 적합합니다. 결과 종합 단계에서는 중복, 상충되는 주장과 출처를 처리해야 합니다.

### Handoff 패턴

```text
상담 Agent → 기술 문제 발견 → 기술 지원 Agent로 인계
```

현재 Agent가 더 적합한 역할에 대화와 필요한 State를 넘깁니다. 전체 내부 Context를 그대로 넘기기보다 업무에 필요한 최소 정보만 전달해야 합니다.

## 11. 여행 예제에 적용하기

### Single Agent가 적절한 단계

현재 여행 실습은 다음 구조이므로 Single Agent가 적절합니다.

```text
Travel Agent
├─ 날씨 조회 Tool
├─ 관광지 검색 Tool
├─ 호텔 검색 Tool
├─ 사용자에게 추가 질문
└─ 일정 추가 Tool
```

근거:

- 사용자의 목표가 여행 계획 하나입니다.
- Tool 결과가 서로 연결되어 있습니다.
- 하나의 여행 Context와 State를 공유합니다.
- 역할별 전문 지침과 권한 차이가 크지 않습니다.
- 작업이 대부분 순차적입니다.

### Multi-Agent를 고려할 만큼 커진 단계

다음 요구사항이 생기면 역할 분리를 고려할 수 있습니다.

```text
Travel Coordinator
├─ 여행 조사 Agent
│  ├─ 날씨·관광지·호텔 조사
│  └─ 읽기 전용 권한
├─ 예산 Agent
│  ├─ 교통·숙박 비용 계산
│  └─ 예산 최적화 기준
├─ 일정 Agent
│  ├─ 이동 시간·일정 충돌 검사
│  └─ 캘린더 읽기 권한
└─ 예약 Agent
   ├─ 실제 예약 요청
   └─ 사용자 승인 후 제한된 변경 권한
```

여기서는 조사, 예산 최적화, 일정 충돌 해결과 예약이 서로 다른 목표와 평가 기준을 가집니다. 또한 예약 Agent의 권한을 읽기 전용 Agent와 분리할 이유가 있습니다.

그래도 예약 승인, 결제와 권한 검증은 LLM Agent가 아니라 Backend Workflow가 최종적으로 보장해야 합니다.

```text
예약 Agent의 실행 제안
   ↓
Backend Schema 검증
   ↓
사용자 명시적 승인
   ↓
권한·가격·재고 재검증
   ↓
예약 Tool 실행
```

## 12. Multi-Agent의 비용과 위험

Agent를 나누면 전문성과 격리를 얻을 수 있지만 다음 비용도 함께 증가합니다.

- Model 호출 수와 사용 비용
- Agent 사이의 전달 지연
- 서로 다른 Agent 결과의 충돌
- 잘못된 작업 위임과 책임 불명확성
- 더 많은 Prompt와 Schema 유지보수
- 조합별 테스트 사례 증가
- 실행 Trace와 장애 분석의 복잡성
- 동일 정보를 여러 Agent가 반복 조회하는 낭비

따라서 Multi-Agent 도입 전후를 같은 평가 Scenario로 비교해야 합니다.

```text
정확도와 업무 완료율
Tool 선택 성공률
평균 Model 호출 수
평균 실행 시간과 비용
잘못된 권한 사용 횟수
재시도와 무한 반복 발생 여부
```

분리 후 품질 향상이 비용과 복잡성 증가보다 작다면 Single Agent가 더 좋은 설계입니다.

## 13. 최종 의사결정 규칙

```text
한 가지 작업만 수행한다
└─ Tool 또는 일반 함수

순서와 조건이 명확하다
└─ Workflow

하나의 목표에서 다음 행동을 동적으로 선택한다
└─ Single Agent + 여러 Tool

독립적인 목표·Context·권한·평가 기준이 여러 개다
└─ Multi-Agent 검토

보안·결제·승인·동시성처럼 결정적 보장이 필요하다
└─ Agent가 아니라 Backend Policy와 Workflow
```

가장 실용적인 원칙은 다음과 같습니다.

> Tool 수가 아니라 독립적인 목표, 판단, Context, 권한과 완료 조건의 경계가 있는지를 보고 Agent를 나눕니다.

기본 전략은 다음과 같습니다.

```text
가능하면 Single Agent
필요하면 Workflow로 통제
명확한 분리 근거가 생긴 역할만 Multi-Agent
중요한 업무 규칙과 권한은 Backend가 보장
```

먼저 `Single Agent + Multi-Tool + State`를 충분히 구현하고 평가한 다음, 실제 한계가 확인된 부분만 여러 Agent로 분리하는 것이 가장 안전합니다.

## 14. Agent별 권한 설계

Agent를 나누었다면 이름만 구분하지 말고 각 Agent의 실행 계약을 명시합니다.

| 항목 | 설명 |
| --- | --- |
| Goal | 이 Agent가 달성해야 하는 한정된 목표 |
| Allowed Tools | 호출할 수 있는 Tool Allowlist |
| Data Scope | 읽을 수 있는 사용자·조직·문서 범위 |
| Change Permission | 조회·초안·변경·금지 중 허용 범위 |
| Input Schema | 다른 Agent나 사용자에게 받을 구조화 입력 |
| Output Schema | 다음 단계로 전달할 구조화 결과 |
| Max Steps | 반복과 Model 호출의 상한 |
| Completion | 완료·대기·실패를 판단하는 조건 |

예를 들어 Multi-Agent 여행 시스템의 권한은 다음처럼 나눌 수 있습니다.

| Agent | Goal | 허용 Tool | 데이터 범위 | 변경 권한 |
| --- | --- | --- | --- | --- |
| Research Agent | 여행 근거 수집 | 날씨·장소·호텔 검색 | 공개 정보 | 없음 |
| Schedule Agent | 충돌 없는 일정 초안 | 캘린더 조회·초안 | 로그인 사용자 일정 | 초안만 |
| Booking Agent | 승인된 예약 요청 | 예약 조회·요청 | 선택한 예약 항목 | 사용자 승인 후 |

Coordinator가 작업을 위임했더라도 Worker의 권한이 자동으로 커지지 않아야 합니다. 다른 Agent의 메시지도 사용자 입력과 마찬가지로 검증되지 않은 데이터이므로 Tool Allowlist, Schema, 소유권과 승인 검사를 우회할 수 없습니다.

## 15. Agent 자율성 단계

| 단계 | Agent 행동 | 예시 | 필요한 통제 |
| ---: | --- | --- | --- |
| 0 | 답변만 생성 | 문서 요약 | 출력 검증 |
| 1 | 읽기 Tool 사용 | 날씨·RAG 검색 | Allowlist·데이터 범위 |
| 2 | 초안 생성 | 이메일·일정 초안 | 사용자 검토 가능성 |
| 3 | 변경 제안 | 일정 등록·메시지 전송 | 명시적 사용자 승인 |
| 4 | 제한된 자동 변경 | 승인된 반복 업무 | 한도·정책·Audit Log |
| 5 | 고위험 작업 | 결제·권한 변경 | 금지 또는 강한 인증·별도 통제 |

자율성은 Agent의 능력에 맞춰 최대한 높이는 값이 아닙니다. 업무 위험과 복구 가능성을 보고 필요한 최소 수준으로 정합니다.
