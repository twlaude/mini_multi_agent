# TRAVEL_ROUTE_MASTER.md — 여행 루트 추천 (2-4)

> 2026-08-19 수업 기반 신규 기능의 **마스터 문서**.
> 상세 구현 계획은 `backend/plan.md` / `frontend/plan.md` 참조.

## 한 문장 정의

사용자가 출발지·도착 도시·기간·시간을 선택하면 LLM이 **정해진 스키마**로
랜드마크·맛집을 뽑아 동선을 카카오맵에 표시하고, 이어지는 교통편 질문은
**조회 전용 Tool Use**로 대중교통 또는 자가용 경로를 답하는 페이지다.

```
출발지 3택 + 도착 도시 + 날짜/시간
  → LLM Structured Output (landmark + food + 일차별 동선)
  → 카카오 로컬 API 지오코딩 (장소명 → 좌표)
  → 지도 렌더 (origin/landmark/food 마커 + 일차별 경로선)
  → 교통편 질문
  → Tool 선택 → 서버 좌표·시각 주입 → ODsay/카카오모빌리티 조회 → 답변
```

## 오늘 수업 핵심 요소 → 이 기능에 반영되는 지점

| 수업 자료 (05/02_prompt-and-structured-output) | 배운 것 | 이 기능에서 쓰는 곳 |
| --- | --- | --- |
| `00_prompt_components` / `01_prompt_template` | 역할·지시·맥락·제약 4요소, 변수 템플릿 | 여행 플래너 system prompt 구성 (목적지/몇박며칠 변수 주입) |
| `02_zero_shot_few_shot` | few-shot으로 출력 형태 고정 | 필요 시 landmark/food 예시 1개를 프롬프트에 포함 |
| `03_delimiters_and_prompt_injection` | 구분자·인젝션 방어 | 사용자 입력을 구분자로 감싸서 전달 |
| `04_system_and_user_messages` | system/user 역할 분리 | system=플래너 규칙, user=여행 요청 |
| `06_prompt_to_structured_output` | 프롬프트 → JSON 계약 | `/api/travel/route-plan`의 출력 계약 |
| `07_pydantic_validation` / `08_travel_structured_output` | Pydantic으로 LLM 출력 검증 (`extra="forbid"`, Field 제약) | `TravelRoutePlan` 스키마 검증 — 기존 `TravelPlan` 확장판 |
| mini_agent_02 기존 코드 | provider 추상화(`generate_structured`), 라우터/서비스 분리, `core/api_client.py` 패턴 | 그대로 재사용 — 새 provider 안 만듦 |

## 2단계 — 입력 구조화 + 교통편 툴콜

### 입력 구조화

- 출발지는 브라우저 위치, 카카오 장소 검색 후보, 국내 도시 목록 중 하나를 사용자가 확정한다.
- 도착지는 `GET /api/travel/cities` 목록에서 고르고 기간은 날짜 range, 출발·종료 시각은 별도 입력한다.
- `POST /api/travel/route-plan`은 기존 `message` 요청을 그대로 지원하면서 `origin`, `destination`, `start_date`, `end_date`, `start_time`, `end_time`을 추가로 받는다.
- 날짜 차이와 `nights/days`는 백엔드가 계산해 `schedule`로 echo한다. LLM에 날짜 계산을 맡기지 않는다.
- 구조화 입력은 백엔드가 자연어 요청으로 합성해 `<request>` 구분자로 감싼다. 첫날은 출발 시각 이후, 마지막 날은 종료 시각 이전이라는 제약도 system prompt에 둔다.
- 카카오 장소 검색·역지오코딩은 키 없음, timeout, 외부 오류 때도 빈 결과와 `note`를 반환하는 fail-soft 계약이다.

### 수업 05/03 Tool Use 요소 → 반영 지점

| 수업 요소 | 이 기능의 반영 지점 | 확인할 trace |
| --- | --- | --- |
| Tool 정의는 이름·설명·입력 스키마의 계약 | `GET /api/tools`, `TRANSPORT_TOOL_DEFINITIONS` | `tool_selection` |
| 모델의 Tool Call은 실행 명령이 아니라 제안 | `select_tool()`은 Tool 이름과 선호값만 선택 | `decision.raw_tool_call` |
| 실행 권한은 애플리케이션 allowlist가 보유 | `run_tool()`의 `TOOLS`에 등록된 2개만 실행 | `tool_result`; 미허용은 `TOOL_NOT_ALLOWED` |
| 모델 인자를 그대로 신뢰하지 않음 | 좌표·출발 시각을 제거한 뒤 request body 값으로 덮어씀 | `argument_injection`, `source=request_body` |
| 실행 전 Pydantic 검증 | 좌표 포함 `TransitRouteArgs`/`DrivingRouteArgs`, `extra="forbid"` | 실패 시 `TOOL_VALIDATION_ERROR` |
| Tool Result를 근거로 최종 답변 | 실 Provider는 “Tool Result 값만 사용” 지시로 답변 생성 | `final_answer` |
| 외부 장애를 전체 요청 실패로 확대하지 않음 | ODsay/카카오모빌리티 빈 결과·note, 안전 실행 결과 | HTTP 200 + 안내 답변 |

### Tool 2개 계약

| Tool | LLM이 제안하는 값 | 서버가 강제 주입하는 값 | 실행 결과 |
| --- | --- | --- | --- |
| `get_transit_route` | `mode: all\|train\|bus\|air` | 출발/도착 위경도, 출발 시각 | ODsay의 기차·버스·항공 옵션, 요금, 시간, 배차 정보 |
| `get_driving_route` | `fuel_efficiency_kmpl`, `fuel_price_per_liter` | 출발/도착 위경도, 출발 시각 | 카카오모빌리티 거리·시간·톨비·유류비·택시비 |

두 Tool은 조회 전용이며 예약·결제 권한이 없다. LLM에 노출되는 Preference 스키마에는 좌표가 없고, 실행 직전에만 좌표 포함 Args로 검증한다.

### 좌표 주입 불변 원칙

```text
LLM 제안 arguments
  → origin_lat/origin_lng/dest_lat/dest_lng/departure_time 제거
  → TravelTransportRequest body의 좌표·시각 주입
  → allowlist Tool 선택 확인
  → 좌표 포함 Args Pydantic 검증
  → 외부 조회
```

LLM이 좌표나 출발 시각을 임의로 포함해도 항상 body 값으로 덮어쓴다. 이 원칙은 환각 좌표로 외부 API를 호출하지 않게 하는 서버 경계이며 프런트 trace에서 사용자에게 보여준다.

## 정해진 답변 스키마 (핵심 계약)

LLM 답변 주제는 **landmark / food 두 개 고정**, 각각 필수 필드 고정 (`extra="forbid"`).

```python
class LandmarkItem(BaseModel):          # 랜드마크 1곳
    name: str                           # 장소명 (지오코딩 검색어로도 사용)
    summary: str                        # 한 줄 설명
    category: str                       # 유형 (해변/사찰/전망대 등)
    day: int                            # 몇일차 방문 (1~days)
    visit_order: int                    # 그 날 방문 순서 (1부터)
    stay_minutes: int                   # 권장 체류 시간(분)
    tip: str                            # 방문 팁 (운영시간/주의사항)

class FoodItem(BaseModel):              # 맛집 1곳
    name: str                           # 상호명 (지오코딩 검색어로도 사용)
    cuisine: str                        # 음식 종류
    signature_menu: str                 # 대표 메뉴
    price_range: str                    # 가격대 (예: "1~2만원")
    day: int                            # 몇일차
    meal_time: Literal["아침","점심","저녁"]
    near_landmark: str                  # 인접 랜드마크명 (동선 연결용)

class TravelRoutePlan(BaseModel):       # 전체 응답
    destination: str                    # 목적지
    nights: int                         # N박
    days: int                           # M일
    summary: str                        # 여행 컨셉 한 줄
    landmarks: list[LandmarkItem]       # 일차당 2~3곳
    foods: list[FoodItem]               # 일차당 2곳 (점심/저녁)
```

지오코딩 후 백엔드가 각 항목에 `lat/lng/address`를 붙여서 내려준다 (프론트는 좌표 계산 안 함).

## 지도 API 결정

- **지오코딩(장소명→좌표): 카카오 로컬 키워드 검색** (`dapi.kakao.com/v2/local/search/keyword.json`) — REST 키 하나로 끝, 상호명 검색 정확도 높음
- **지도 렌더: 카카오맵 JS SDK**를 `st.components.v1.html`로 임베드 — 마커 + 일차별 색깔 polyline
  - 필요: 카카오 JavaScript 키 + 카카오 개발자 콘솔에 `http://localhost:8501` 도메인 등록
  - 폴백: 네이버 Static Map(이미지) — JS 키 등록이 막히면 이걸로
- 키 위치: VPS `~/Scripts/.env`의 `KAKAO_REST_KEY` 등 → 프로젝트 `.env`에 `KAKAO_REST_KEY`, `KAKAO_JS_KEY` 복사해서 사용 (커밋 금지, `.env.example`에 키 이름만 추가)

## 규모 상한 (과설계 방지)

- 2단계 백엔드 신규/수정 합계 약 400줄, 테스트 약 8개 범위
- 프런트는 페이지 1개와 기존 클라이언트·지도 컴포넌트의 최소 확장
- 새 provider/새 인프라/캐싱/DB/재시도/백그라운드 작업 없음
- 외부 조회 실패는 빈 결과와 안내로 제한하고 기존 여행 카드까지 숨기지 않음

## 문서 지도

- `backend/plan.md` — 엔드포인트/스키마/서비스 구현 계획
- `frontend/plan.md` — 페이지/클라이언트/지도 임베드 구현 계획
