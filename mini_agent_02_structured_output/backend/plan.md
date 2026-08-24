# plan.md — 여행 루트 추천 Backend (2-4)

> 마스터 문서: `../TRAVEL_ROUTE_MASTER.md` (스키마 계약·지도 API 결정은 거기가 SSOT)

## 목표

기존 자연어 `POST /api/travel/route-plan` 계약을 유지하면서 출발지·도착지·기간·시간의 구조화 입력을 받고, 추천 뒤 교통편 질문은 조회 전용 ODsay/카카오모빌리티 Tool Use로 답한다. 외부 API 실패는 여행 카드나 전체 요청을 500으로 만들지 않는다.

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

## 2단계 구현 상태 — 입력 구조화 + 교통편 Tool Use (2026-08-20)

### 입력·장소 보조 API

| 파일 | 구현 상태 |
| --- | --- |
| `app/schemas.py` | `OriginPoint`, 구조화 필드를 포함한 `TravelRouteRequest`, `TravelSchedule`, `PlaceCandidate`, `ReverseGeocodeResult`, `CityItem`; `GeoPlace.kind="origin"`; `TravelRouteResult.origin/schedule` 구현 |
| `app/data/cities.py` | 국내 25개 도시 이름과 중심 좌표 구현 |
| `app/services/kakao_service.py` | 후보 검색·역지오코딩·기존 계획 지오코딩 재사용, 전부 fail-soft 구현 |
| `app/routers/structured_router.py` | `/api/travel/cities`, `/places/search`, `/places/reverse`; 구조화 route 요청 합성, 날짜 계산, origin/schedule echo 구현 |
| `app/providers.py` | mock 목적지 인식을 25개 도시로 확장, 기존 message 계약 유지 |

구조화 route 입력은 `destination + start_date + end_date`가 한 묶음이며 `message`를 추가 요청으로 함께 보낼 수 있다. 날짜 차이와 29박 30일 상한은 서버가 검증하고, LLM에는 `<request>` 구분자로 합성문을 전달한다.

### 교통 Tool Use

| 파일 | 구현 상태 |
| --- | --- |
| `app/schemas.py` | LLM 노출용 `TransitRoutePreference`/`DrivingRoutePreference`와 실행용 좌표 포함 Args를 분리 |
| `app/tools/definitions.py` | `get_transit_route`, `get_driving_route` 정의; LLM 스키마에 좌표를 노출하지 않음 |
| `app/tools/transport_tools.py` | 2개 함수만 허용하는 `TOOLS` allowlist와 `run_tool()` 구현 |
| `app/services/odsay_service.py` | 도시간 기차·버스·항공 정규화, mode 필터, type별 시간순 상위 3개, KTX/SRT 등 열차 코드 라벨 구현 |
| `app/services/kakao_mobility_service.py` | 현재/미래 길찾기, 거리·시간·톨비·유류비·합계 정규화 구현 |
| `app/providers.py` | mock/openai/gemini Tool 선택 구현, ollama 미지원 명시, 교통 질문 Tool 선택 instruction 구현 |
| `app/routers/transport_router.py` | `/api/tools`, `/api/tools/run`, `/api/travel/transport`; 안전 실행·body 좌표 강제 주입·trace·최종 답변 구현 |
| `app/config.py`, `.env.example` | `ODSAY_KEY`, 연비·유가 기본값 설정 구현; `.env.example`에 키 이름만 유지 |

좌표·출발 시각은 LLM의 기존 제안 인자에서 제거한 뒤 `TravelTransportRequest` body 값으로 덮어쓴다. allowlist 확인과 좌표 포함 Args 검증을 통과한 Tool만 실행한다. 모든 Tool은 조회 전용이며 예약·결제를 하지 않는다.

### 2.5 실스모크 결함 보완

- LLM 노출 스키마에서 필수 좌표를 제거해 교통편 질문만으로도 Tool을 선택할 수 있게 했다.
- openai/gemini 선택 instruction에 교통편 질문이면 Tool 하나를 호출하고 선호값만 채우도록 명시했다.
- ODsay `trainType` 코드 `8`을 SRT로 표시하고 기존 출발역 휴리스틱을 제거했다.
- Tool 미선택 안내를 `tool_choice="none"`과 일반 선택 실패로 구분했다.
- Gemini 실검증에서 “고속버스로 가면 얼마야?”가 `get_transit_route`, `mode="bus"`를 선택하고 실행한 것을 확인했다.

## 최종 검증 (2026-08-20)

### 자동 테스트

```bash
cd mini_agent_02_structured_output/backend
../.venv/bin/python -m pytest -q
```

- 결과: `25 passed in 9.18s`
- 기존 16개 회귀와 구조화 입력·장소 보조·ODsay/Kakao 정규화·allowlist·인자 검증·좌표 덮어쓰기 테스트를 모두 포함한다.
- 테스트의 외부 HTTP는 monkeypatch이며, 아래 실스모크와 증거 범위를 구분한다.

### 실키 curl 스모크

프로젝트 `.env`의 `LLM_PROVIDER=mock`, `KAKAO_REST_KEY`, `ODSAY_KEY` 설정을 사용해 로컬 uvicorn `127.0.0.1:8000`에 실제 curl로 호출했다. 실키 값은 출력·문서·커밋에 포함하지 않았다.

| 호출 | 결과 |
| --- | --- |
| `GET /api/travel/cities` | 200, 국내 도시 25개 |
| `GET /api/travel/places/search?query=서울역` | 200, 후보 5개; 첫 후보 `서울역`, `서울 중구 한강대로 405` |
| `GET /api/travel/places/reverse?lat=37.5547&lng=126.9707` | 200, `서울특별시 용산구 남영동`, region `서울특별시` |
| `POST /api/travel/route-plan` 구조화 mock | 200, 부산 2박 3일, `schedule` 2박/3일, 서울역 `origin`, 장소 5/5 지오코딩 |
| `GET /api/tools` | 200, 조회 전용 Tool 2개, LLM input schema에 좌표 없음 |
| `POST /api/travel/transport` “KTX로 가면?” | 200, `get_transit_route`, `mode=train`; SRT 130분 52,200원, KTX 138분 59,800원 등 ODsay 실결과 |
| `POST /api/travel/transport` “차로 가면?” | 200, `get_driving_route`; 408.7km/311분, 톨 22,000원, 유류비 56,198원, 합계 78,198원 |

두 교통 응답 모두 `tool_selection → argument_injection → tool_result → final_answer` trace와 request body 좌표·출발 시각 주입을 포함했다. 실스모크 종료 후 uvicorn 프로세스를 종료했다. 축약한 실제 JSON은 `frontend/plan.md`의 endpoint 계약에 기록했다.
