# plan_backend.md — 백엔드 구현 (담당: 성엽)

> **과제 본질 한 문장**: 주차 출입 시스템 — 번호판 인식 → 출입 판단 → 게이트 열림/닫힘 신호. **워크플로우 버전(고정 룰)** 과 **AI 에이전트 버전(Ollama tool-calling)** 두 벌을 같은 DB 위에서 만든다.
> **규모 상한**: 라우터 2개(parking_workflow, parking_agent) + 서비스/툴 파일 ~4개. 파일당 ~200줄 이내.

## 0. 공통 아키텍처 (3명 공유 — 이 블록은 세 plan 모두 동일)

```
[카메라(웹캠) → 번호판 OCR]  ──plate 문자열──▶  [FastAPI 백엔드]  ──SQL──▶  [Docker PG]
        (오현님)                                   (성엽)                    (태웅)
                                                     │
                          워크플로우 버전: if/else 고정 룰
                          에이전트 버전:  Ollama(도커, 오현님 세팅)가 툴 골라 쓰며 판단
                                                     │
                                            [Streamlit 프론트] (오현님)
```

- **기능 3개** (두 버전 각각 구현): ① 외부인 차량 조회 ② 이상 시간대 출차 → 음주 체크 ③ 꼬리물기 탐지
- **작업 위치**: 이 repo의 `mini_agent_02_structured_output/backend/` — 수업 뼈대 패턴(`app/domains/<도메인>/router.py + service.py + schemas.py` 계층) 그대로 새로 구성
- **응답 봉투**: `{"success": bool, "message": str, "data": ...}` 유지
- **DB**: `postgresql://parking:parking@<태웅IP>:5435/parking` (.env `PARKING_DSN`으로 주입) — supabase 클라이언트 대신 **psycopg** 직접 사용 (`app/core/db.py` 하나 만들어서 connection 헬퍼)
- **Ollama**: `http://<오현님IP>:11434/v1/chat/completions` (OpenAI 호환, .env `OLLAMA_URL`로 주입) — 오현님 컴에서 돌고 백엔드가 원격 호출. **모델 `llama3.2` 확정** (2026-08-24 현장 결정 — 오현님 컴에 이미 설치돼 있고 tool calling 지원). 스키마는 plan_db.md가 SSOT.
- **배포 방식: git 없음 + 역할별 분산 호스팅** — 같은 네트워크에서 각자 담당만 자기 컴에 띄우고 서로 IP로 접속 (태웅=DB:5435 / 성엽=백엔드:8000 / 오현님=프론트+Ollama:11434+카메라). **백엔드는 반드시 `uvicorn app.main:app --host 0.0.0.0 --port 8000`** — 오현님이 원격으로 붙어야 하니 127.0.0.1 바인딩 금지. IP들은 .env로 주입, 계약(경로·포트·스키마) 임의 변경 금지
- ⚠️ 와이파이가 기기 간 통신 막으면 폰 핫스팟 폴백. OS 방화벽 8000 인바운드 허용 필요할 수 있음

## 1. 도메인 구조 (두 버전을 도메인으로 분리 — 데모 때 나란히 비교)

```
app/domains/parking_workflow/   # 버전 A: 코드만
  router.py  service.py  schemas.py
app/domains/parking_agent/      # 버전 B: AI 에이전트
  router.py  agent_service.py  tools.py  schemas.py
app/core/db.py                  # psycopg 커넥션 헬퍼 (공용)
```

## 2. 공용 엔드포인트 (카메라/시뮬레이터가 쏘는 입력단 — 버전 무관)

| 메서드 | 경로 | 몸체 | 설명 |
|---|---|---|---|
| POST | `/parking/{mode}/gate` | `{plate, direction}` | mode=workflow\|agent. 입출차 판단 → `{decision, reason}` 반환 + gate_events 기록 |
| POST | `/parking/spot-event` | `{spot_id, plate, event}` | 자리 센서 시뮬레이션 입력 (spot_events 적재) |
| POST | `/parking/sobriety/{check_id}` | `{result: pass\|fail}` | 가짜 음주측정 결과 입력 (프론트 버튼이 호출) |
| GET | `/parking/{mode}/visitors` | - | 기능① 현재 주차중 외부인 목록 |
| GET | `/parking/{mode}/tailgating` | - | 기능③ 꼬리물기 의심 목록 |
| GET | `/parking/status` | - | 대시보드용: 주차면 점유 현황 + 최근 이벤트 + 미해결 alerts |

## 3. 버전 A — 워크플로우 (고정 룰, LLM 없음)

- **기능① 외부인 조회**: SQL 한 방 — 마지막 gate_events가 enter인데 vehicles에 없는 plate
- **기능② 출차 판단** (`direction=exit`일 때 고정 순서):
  1. 과거 30일 해당 plate의 출차시각 avg/stddev 계산 (이력 5건 미만이면 스킵하고 open)
  2. 현재 시각이 `평균±2h` 밖이거나 00~05시 → sobriety_checks pending 생성, `decision=hold` 반환
  3. 측정 결과가 pass로 들어오면 재시도 시 open, fail이면 deny + alerts(drunk_suspect)
- **기능③ 꼬리물기**: spot_events에 occupied로 등장했는데 그 이전 24h 내 gate enter 기록 없는 plate → alerts(tailgating) upsert
- reason 필드에 어떤 룰에 걸렸는지 문자열로 기록 (`"룰2: 평소 19시 출차, 현재 03시"`)

## 4. 버전 B — AI 에이전트 (Ollama tool-calling)

`tools.py`에 파이썬 함수 5개 정의하고 OpenAI tools 스펙으로 노출:

| 툴 | 하는 일 |
|---|---|
| `lookup_vehicle(plate)` | 등록 여부 + 소유주 |
| `get_exit_history(plate)` | 최근 30일 출차 시각 목록 |
| `get_gate_entry(plate)` | 최근 입차 기록 유무 (꼬리물기 판단용) |
| `request_sobriety_check(plate)` | 가짜 음주측정 요청 생성 |
| `create_alert(type, plate, detail)` | 경보 기록 |

- `agent_service.py`: 시스템 프롬프트에 "너는 주차장 관제 에이전트. 툴을 사용해 조사하고 최종적으로 `{decision, reason}` JSON으로 답하라" + tool-call 루프 (최대 5턴, 초과 시 안전하게 deny)
- 게이트 요청이 오면 에이전트가 **스스로** 이력 조회 → 이상 시간대 판단 → 음주측정 요청 여부 결정. 워크플로우와 달리 ±2h 같은 임계값이 코드에 없고 LLM 판단 + 프롬프트 가이드라인만 있음 → 이게 데모 포인트
- 기능①/③도 동일: `/parking/agent/visitors`는 자연어 질의 라우트 `/parking/agent/ask` (`{question}`) 하나로 통합해도 됨 — 관제 챗봇으로 데모 (프론트 채팅탭과 연결)
- ⚠️ Ollama 소형 모델은 tool-call이 가끔 삑나니까: JSON 파싱 실패 시 1회 재시도 → 그래도 실패면 워크플로우 버전으로 폴백하고 reason에 `"agent 실패 → workflow 폴백"` 명시. 데모 안정성 확보.

## 5. 단계
1. `app/core/db.py` + 헬스체크에 DB ping 추가 (태웅 DB 뜨면 바로 검증)
2. 버전 A 워크플로우 3기능 (여기까지가 오전 목표 — 이것만 있어도 데모 가능)
3. 공용 입력단 (spot-event, sobriety)
4. 버전 B 에이전트 (Ollama 연결 → 툴 5개 → 게이트 판단 → ask 챗)
5. 시딩 데이터 기준 시나리오 테스트: 정상 출차 / 새벽 출차→hold→pass→open / 꼬리물기 탐지

## 6. 완료 기준
- [ ] `POST /parking/workflow/gate` 새벽 출차 시나리오에서 hold → 측정 pass 후 open
- [ ] `POST /parking/agent/gate` 같은 시나리오에서 LLM reason이 자연어로 기록됨
- [ ] `/parking/{mode}/tailgating`이 시딩된 '99허9999' 잡아냄
- [ ] 에이전트 실패 시 폴백 동작 확인 (Ollama 끈 상태로 한 번 호출)

## 7. 금지사항
- LangChain/LangGraph 등 프레임워크 도입 금지 — httpx로 Ollama 직접 호출 (실습 규모에 과함)
- 두 버전이 서로의 코드 import 금지 (비교 데모가 목적이라 섞이면 안 됨). 단 db.py·schemas 공용은 OK
