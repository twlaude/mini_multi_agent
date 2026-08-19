# plan.md — 여행 루트 추천 Backend (2-4)

> 마스터 문서: `../TRAVEL_ROUTE_MASTER.md` (스키마 계약·지도 API 결정은 거기가 SSOT)

## 목표

`POST /api/travel/route-plan` 하나로:
자연어 여행 요청 → LLM Structured Output(`TravelRoutePlan`) → 카카오 지오코딩으로 좌표 부착 → 프론트가 바로 지도에 찍을 수 있는 JSON 반환.

## 설계

### 스키마 (`app/schemas.py`)

| 모델 | 역할 |
| --- | --- |
| `LandmarkItem` / `FoodItem` / `TravelRoutePlan` | 마스터 문서의 계약 그대로 (`extra="forbid"`) |
| `TravelRouteRequest(MessageRequest)` | `provider: ProviderName \| None` 추가 — 기존 `StructuredOutputRequest` 패턴 |
| `GeoPlace` | 지오코딩 결과: `name, lat, lng, address, found: bool, kind: Literal["landmark","food"], day, order` |
| `TravelRouteResult` | `provider, model, plan: TravelRoutePlan, places: list[GeoPlace], not_found: list[str], latency_ms` |

- `StructuredSchemaName`에 `"travel_route"` 추가 → `get_structured_model()` 매핑에 `TravelRoutePlan` 등록 (기존 travel_plan/support_ticket과 같은 방식 — mock 분기도 1개 추가)

### 서비스 (`app/services/kakao_service.py` 신규)

| 함수 | 내용 |
| --- | --- |
| `geocode_place(query, region) -> GeoPlace \| None` | 카카오 로컬 키워드 검색. 검색어 = `f"{destination} {name}"` (지역명 붙여 정확도 확보). 1건도 없으면 None |
| `geocode_plan(plan) -> tuple[list[GeoPlace], list[str]]` | landmarks + foods 순회 (근처 맛집이니 개수 적음 — 순차 호출로 충분). 실패 항목은 `not_found`로 분리, 재시도 없음 |

- `httpx` 사용 (이미 requirements에 있으면 그대로, 없으면 추가), timeout 5초
- `config.py`에 `kakao_rest_key: str = ""` 추가 (`.env`의 `KAKAO_REST_KEY`)

### 라우터 (`app/routers/structured_router.py`에 추가)

```
@structured_router.post("/api/travel/route-plan", response_model=TravelRouteResult)
```

1. `generate_structured(provider, system_prompt, message, "travel_route")` — 기존 함수 그대로
2. `TravelRoutePlan.model_validate(...)` 검증 (기존 패턴)
3. `geocode_plan()` 좌표 부착 → `TravelRouteResult` 반환
4. 에러 처리 기존 패턴 유지: ValueError→422, 그 외→502. **카카오 API 실패는 500 내지 말고 `places=[]` + `not_found` 전체로 응답** (LLM 결과만이라도 보여주기)

### System Prompt (수업 내용 반영 지점)

- 역할·지시·제약 4요소 구성 (00~01), 사용자 입력은 구분자로 감싸기 (03)
- 제약 명시: "landmark는 일차당 2~3곳, food는 일차당 점심/저녁 2곳, 실존 장소만, day는 1~{days}"
- `near_landmark`는 landmarks에 있는 이름만 쓰도록 지시 (동선 연결 일관성)

## 구현 단계

1. [x] `.env`/`.env.example`에 `KAKAO_REST_KEY` 추가 (실키는 VPS `~/Scripts/.env`에서 복사, 커밋 금지)
2. [x] `schemas.py`: 스키마 5종 추가 + `StructuredSchemaName` 확장
3. [x] `providers.py`: `get_structured_model` 매핑 + mock 분기 추가
4. [x] `services/kakao_service.py`: 지오코딩 2함수
5. [x] `structured_router.py`: `/api/travel/route-plan` 추가
6. [x] 테스트 (`tests/test_api.py`): mock provider + 카카오 호출 monkeypatch로 정상 1개, 지오코딩 실패 1개
7. [x] 검증: `pytest` 통과 + OpenAPI(`/docs`)에 라우트 확인

## 완료 기준

- mock provider로 `POST /api/travel/route-plan` → 좌표 붙은 JSON 응답
- gemini/openai 실 provider 1개로 "부산에 2박 3일" 실호출 성공
- 카카오 키 없거나 API 죽어도 LLM 결과는 응답됨 (fail-soft)

## 구현 결과 (2026-08-19 완료)

- 테스트 16개 통과 (기존 14 + 신규 2), gemini 실호출 "여수 1박 2일" → 랜드마크 5 + 맛집 4, 카카오 지오코딩 9/9 성공
- ⚠️ 발견한 Gemini quirk: `$defs` 객체 리스트가 2개 이상인 스키마에 리스트 `minItems/maxItems`가 있으면 400 INVALID_ARGUMENT.
  → `providers.py`의 `_gemini_safe_schema()`가 생성용 스키마에서만 minItems/maxItems를 제거 (개수 검증은 Pydantic이 응답 파싱 시 수행 — 계약 유지)
