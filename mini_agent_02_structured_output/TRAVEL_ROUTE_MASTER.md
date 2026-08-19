# TRAVEL_ROUTE_MASTER.md — 여행 루트 추천 (2-4)

> 2026-08-19 수업 기반 신규 기능의 **마스터 문서**.
> 상세 구현 계획은 `backend/plan.md` / `frontend/plan.md` 참조.

## 한 문장 정의

사용자가 "부산에 2박 3일 여행 가"라고 입력하면, LLM이 **정해진 스키마**로
랜드마크·맛집을 뽑아주고, 그 동선을 **카카오/네이버 지도**에 마커 + 경로로 찍어주는 페이지.

```
자연어 입력 → LLM Structured Output (landmark + food + 일차별 동선)
           → 카카오 로컬 API 지오코딩 (장소명 → 좌표)
           → 지도 렌더 (마커 + 일차별 경로선)
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

- 백엔드 신규 ~150줄 (스키마 + 서비스 + 라우터), 테스트 2~3개
- 프론트 신규 ~150줄 (페이지 1개 + 클라이언트 함수 1개 + 지도 HTML 템플릿)
- 새 provider/새 인프라/캐싱/DB 없음. 지오코딩 실패한 장소는 지도에서 빼고 경고만 표시 (재시도 로직 없음)

## 문서 지도

- `backend/plan.md` — 엔드포인트/스키마/서비스 구현 계획
- `frontend/plan.md` — 페이지/클라이언트/지도 임베드 구현 계획
