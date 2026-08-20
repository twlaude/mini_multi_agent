# plan.md — 여행 루트 추천 Frontend 2단계 구현 계약서 (2-4)

> 백엔드(twmoon)는 프론트 파일을 수정하지 않는다. 이 문서가 계약이다.

> 마스터 문서: `../TRAVEL_ROUTE_MASTER.md`
> 백엔드 구현 기록: `../backend/plan.md`
> 대상 페이지: `app_pages/12_travel_route.py`
> 이 문서는 프런트 담당자가 백엔드 코드를 열지 않고도 구현할 수 있는 자기완결 계약서다.

## 1. 한 문장 목표

사용자가 **출발지를 브라우저 위치·주소 검색·도시 목록 중 하나로 확정**하고 목적지·기간·시간을 선택하면 일차별 여행 카드와 카카오맵 동선을 보여주고, 이어서 “KTX로 가면?” 또는 “차로 가면?”을 물어 **조회 전용 교통 Tool의 선택→서버 인자 주입→실행→답변 trace**까지 확인하게 한다.

## 2. 전체 UX 흐름

```text
페이지 진입
  → 도시 목록 GET /api/travel/cities 로드
  → 출발지 방식 3택
      ① 브라우저 위치 → GPS → GET /api/travel/places/reverse → OriginPoint 확정
      ② 주소·장소 검색 → GET /api/travel/places/search → 후보 radio → OriginPoint 확정
      ③ 도시 selectbox → cities 좌표 → OriginPoint 확정
  → 도착 도시 + 날짜 범위 + 출발/종료 시간 선택
  → POST /api/travel/route-plan
  → 요약 + 일차별 카드 + not_found 경고 + 카카오맵/좌표표
  → 교통편 질문 입력 또는 예시 버튼
  → POST /api/travel/transport
  → final_answer + Tool trace expander
```

프런트는 좌표를 계산하거나 외부 지도 REST API를 직접 부르지 않는다. 출발지는 사용자가 확정한 `OriginPoint`를 저장하고, 장소 검색·역지오코딩·여행 루트·교통 조회는 모두 FastAPI를 통한다.

## 3. 화면 구역표

| 순서 | 화면 구역 | 위젯과 동작 | 저장할 상태 |
| --- | --- | --- | --- |
| 1 | 제목·안내 | `🗺️ 여행 루트 추천`, “출발지와 일정을 고르면 지도 동선을 만들어요.” | 없음 |
| 2 | 출발지 블록 | `st.radio`로 브라우저 위치/주소·장소 검색/도시 선택 3택. 아래 §4 규칙으로 한 후보를 확정 | `travel_origin: {name, lat, lng}` |
| 3 | 도착·일정 블록 | 도시 `st.selectbox`, `st.date_input` range, 출발·종료 `st.time_input`, 선택 Provider, 선택적 추가 요청 | 요청 payload |
| 4 | 실행 | `여행 루트 만들기` 버튼, `st.spinner`, 입력 검증 후 구조화 요청 | `travel_route_result` |
| 5 | 결과 요약 | 목적지, `schedule.nights/days`, 여행 컨셉, Provider/model/latency | 응답 `plan`, `schedule` |
| 6 | 일차별 카드 | `plan.days`만큼 탭. 랜드마크는 `visit_order`, 음식은 아침→점심→저녁 순 | 응답 `plan` |
| 7 | 지도·좌표 폴백 | origin/landmark/food 마커, 일차별 landmark polyline, 항상 펼칠 수 있는 좌표표 | `origin`, `places` |
| 8 | 교통편 질문 | 추천 아래 `st.text_input`, “KTX로 가면?”, “차로 가면?” 예시 버튼, 조회 버튼 | `transport_result` |
| 9 | 교통 결과 | `final_answer`, 실패 경고, trace expander | `decision`, `tool_result`, `trace` |

결과는 `st.session_state`에 보관해 Streamlit 재실행에도 유지한다. 새 여행 루트를 만들면 이전 교통 결과는 지워서 서로 다른 출발지·목적지 결과가 섞이지 않게 한다.

## 4. 출발지 블록 — 반드시 3택

출발 방식은 한 번에 하나만 활성화한다. 어떤 방식이든 최종 상태는 아래 동일한 구조다.

```python
origin = {"name": "서울역", "lat": 37.5547, "lng": 126.9707}
```

### 4.1 브라우저 위치

`streamlit-js-eval`의 `get_geolocation()`을 사용한다. 프로젝트 공용 `requirements.txt`에는 구현 PR에서 `streamlit-js-eval`을 추가해야 한다. 브라우저 위치 API는 `localhost` 또는 HTTPS에서만 동작하며 사용자가 권한을 거부하면 `None`일 수 있다.

```python
from streamlit_js_eval import get_geolocation

if st.button("📍 현재 위치 가져오기"):
    location = get_geolocation()
    coordinates = (location or {}).get("coords") or {}
    lat = coordinates.get("latitude")
    lng = coordinates.get("longitude")
    if lat is None or lng is None:
        st.warning("위치를 가져오지 못했어요. 장소 검색이나 도시 선택을 이용해 주세요.")
    else:
        reverse = reverse_travel_place(float(lat), float(lng))
        name = reverse.get("address") or f"{float(lat):.4f},{float(lng):.4f}"
        st.session_state.travel_origin = {
            "name": name,
            "lat": float(lat),
            "lng": float(lng),
        }
```

`reverse.note`가 비어 있지 않거나 주소가 없더라도 좌표 자체는 유효하므로 좌표명으로 확정할 수 있다. 권한 거부·비보안 환경·브라우저 미지원은 페이지 오류로 만들지 말고 나머지 두 방식으로 유도한다.

### 4.2 주소·장소명 검색

1. `st.text_input("주소 또는 장소명")`에 “서울역”처럼 입력한다.
2. 검색 버튼에서 `GET /api/travel/places/search?query=...&size=5`를 호출한다.
3. `candidates=[]`이면 `note`를 안내하고 끝낸다.
4. 후보는 `이름 · 주소 · 카테고리` 라벨의 `st.radio`로 표시한다.
5. “이 출발지로 확정” 버튼을 눌러 선택 후보의 `name/lat/lng`를 `travel_origin`에 저장한다.

검색 결과 배열의 첫 항목을 자동 확정하지 않는다. 네이버지도 앱처럼 검색과 후보 확정을 분리한다.

### 4.3 도시 목록 선택

`GET /api/travel/cities`의 `cities`를 selectbox에 표시하고 선택한 항목의 `name/lat/lng`를 그대로 출발지로 사용한다. 검색 실패나 GPS 권한 거부 때 항상 쓸 수 있는 폴백이다.

확정된 출발지는 방식과 무관하게 블록 하단에 `✅ 서울역 (37.5547, 126.9707)`처럼 한 번 더 보여준다.

## 5. 도착 도시·기간·시간 입력

- 도착 도시는 `GET /api/travel/cities` 결과만 selectbox에 표시한다. 선택한 도시 객체는 교통 API의 `destination` 좌표로도 재사용한다.
- 기간은 `st.date_input(..., value=(start_date, end_date))` range로 받는다. 선택 도중 값이 하나뿐이면 실행을 막고 종료일 선택을 안내한다.
- 같은 날 당일치기는 허용된다. 최대는 30일(29박 30일)이다.
- 출발·종료 시각은 각각 `st.time_input`으로 받는다.
- 추가 요청은 선택 입력이다. 예: “바다와 시장 중심”. 구조화 필드와 함께 `message`로 보낼 수 있다.
- Provider 기본값은 “서버 기본값”으로 두고 이 경우 `provider` 필드 자체를 생략한다. 선택지를 노출하면 `mock`, `gemini`, `openai`, `ollama`다.

실행 전 검증:

- 출발지 확정 필수
- 도착 도시 필수
- 날짜 2개 필수, 종료일 ≥ 시작일, 30일 이내
- 출발지와 도착지가 같아도 프런트에서 임의 차단하지 않음

## 6. 여행 결과 렌더링

### 6.1 요약

- 목적지: `schedule.destination` 우선, 없으면 `plan.destination`
- 기간: `schedule.nights`박 `schedule.days`일 우선, 기존 message 응답이면 `plan.nights/days`
- 선택 시간: `schedule.start_time`, `schedule.end_time`이 있을 때만 표시
- 여행 컨셉: `plan.summary`
- 보조 정보: `provider`, `model`, `latency_ms`

### 6.2 일차별 카드

`1..plan.days`를 탭으로 만든다.

랜드마크 카드:

- 해당 `day`만 필터링하고 `visit_order` 오름차순
- 장소명, 한 줄 설명, 카테고리, 권장 체류 시간, 방문 팁

음식 카드:

- 해당 `day`만 필터링하고 아침→점심→저녁 순
- 상호명, 음식 종류, 대표 메뉴, 가격대, 가까운 랜드마크

`places=[]`여도 카드 데이터는 `plan`에 있으므로 카드 UI를 숨기지 않는다. `plan.landmarks`와 `places`를 배열 위치로 결합하지 말고 필요하면 `(name, kind)`로 찾는다.

## 7. 카카오맵과 좌표표

기존 `components/kakao_map.py`의 안전한 JSON 직렬화, 좌표 검증, landmark/food 마커, bounds, 일차별 polyline 동작을 유지하며 origin 지원을 더한다.

### 마커 규칙

- `origin`: 초록색 또는 `O`, “출발지” 정보창, polyline 제외
- `landmark`: 파란색 또는 `L`, `day/order` 표시, 같은 day끼리 polyline 포함
- `food`: 빨간색 또는 `F`, `day` 표시, polyline 제외
- `places`와 응답의 별도 `origin`을 합쳐 지도 입력을 만든다. 원본 응답은 변경하지 않는다.
- 위경도가 숫자가 아니거나 범위를 벗어난 항목만 제외한다.

### 경로선 규칙

1. `kind="landmark"`만 선택한다.
2. `day`별로 묶고 `order` 오름차순으로 정렬한다.
3. 일차별 서로 다른 색상으로 polyline을 그린다.
4. 하루 랜드마크가 1개면 마커만 표시한다.
5. origin과 food는 선에 포함하지 않는다.

### 지도 실패 폴백

- `st.components.v1.html`과 `KAKAO_JS_KEY`를 사용한다.
- `KAKAO_REST_KEY`는 프런트에서 읽거나 브라우저로 전달하지 않는다.
- JavaScript 키 누락, 등록 도메인 오류, SDK 로드 실패는 지도 구역의 경고로 제한한다.
- 지도 아래 `st.expander("좌표로 보기")`의 표에는 `name/kind/day/order/address/lat/lng`를 항상 제공한다. iframe 내부 SDK 실패를 Python이 감지하지 못해도 사용자가 좌표를 확인할 수 있다.
- JSON은 기존 `_safe_json()`처럼 `<`, `>`, `&`를 이스케이프하고 LLM/사용자 문자열을 JavaScript 코드에 직접 연결하지 않는다.

## 8. 교통편 질문과 Tool trace

여행 추천 결과 아래에만 표시한다.

- `st.text_input("교통편 질문", placeholder="KTX로 가면?")`
- 예시 버튼 두 개: `KTX로 가면?`, `차로 가면?`
- 버튼은 질문 값을 채우며 자동 호출하지 않아도 된다.
- 요청 `origin`은 확정 출발지, `destination`은 선택한 도착 도시 객체, `departure_time`은 시작 날짜+출발 시간을 합친 ISO datetime이다.
- 기본 `tool_choice`는 `auto`다.

성공 시 `final_answer`를 가장 먼저 보여준다. 그 아래 `st.expander("Tool 실행 과정")`에서 `trace`를 순서대로 표시한다.

| 실제 stage | 화면 라벨 | 보여줄 핵심 |
| --- | --- | --- |
| `tool_selection` | 1. Tool 선택 | `decision.tool_name`, `reason`, `confidence`, LLM 선호 인자 |
| `argument_injection` | 2. 서버 인자 주입·검증 | `source=request_body`, 서버가 덮어쓴 좌표·출발 시각 |
| `tool_result` | 3. 조회 실행 | `success`, 조회 데이터 또는 `error.code` |
| `final_answer` | 4. 답변 | Tool Result만 사용한 답변 |

이 trace는 수업의 핵심이다. LLM은 `mode`, 연비, 유가 같은 **선호값만 제안**하고 출발지·목적지 좌표와 출발 시각은 라우터가 body 값으로 덮어쓴다는 설명을 함께 표시한다. 예약·결제 기능이 아니라 조회 전용임도 명시한다.

`decision.tool_name is None`, `tool_result is None`, `tool_result.success=false` 모두 정상 JSON일 수 있다. HTTP 200이어도 `success`를 확인하고 실패면 `final_answer`와 함께 경고를 표시한다.

## 9. API 계약 한눈에 보기

기본 URL은 `BACKEND_API_URL`이며 로컬 기본값은 `http://127.0.0.1:8000`이다.

| 메서드 | 경로 | 용도 | 외부 API 실패 |
| --- | --- | --- | --- |
| GET | `/api/travel/cities` | 출발·도착 도시 목록 | 외부 호출 없음 |
| GET | `/api/travel/places/search` | 주소·장소 후보 검색 | 200 + 빈 `candidates` + `note` |
| GET | `/api/travel/places/reverse` | GPS 좌표→행정동 | 200 + 빈 주소/region + `note` |
| POST | `/api/travel/route-plan` | 구조화 또는 기존 message 여행 루트 | 지오코딩 실패는 200 + `places=[]`/`not_found` |
| GET | `/api/tools` | LLM에 노출되는 조회 Tool 정의 | 외부 호출 없음 |
| POST | `/api/tools/run` | allowlist Tool 직접 실행(학습·진단용) | 200 + `success=false` |
| POST | `/api/travel/transport` | Tool 선택·인자 주입·실행·답변 | 200 fail-soft + 안내 답변 |

## 10. 엔드포인트 상세 계약과 2026-08-20 실스모크 예시

아래 응답 값은 로컬 uvicorn과 프로젝트 `.env`의 실키로 받은 응답을 축약한 것이다. 키 값은 포함하지 않는다.

### 10.1 `GET /api/travel/cities`

요청 body는 없다.

```http
GET /api/travel/cities
```

```json
{
  "cities": [
    {"name": "서울", "lat": 37.5663, "lng": 126.9779},
    {"name": "부산", "lat": 35.1797, "lng": 129.075},
    {"name": "제주", "lat": 33.4996, "lng": 126.5312},
    {"name": "서귀포", "lat": 33.2541, "lng": 126.5601}
  ]
}
```

실제 목록은 서울·부산 등 25개 도시다. 받은 순서를 그대로 selectbox 순서로 사용한다.

### 10.2 `GET /api/travel/places/search`

쿼리:

- `query`: 필수, 1~100자
- `size`: 선택, 기본 5, 1~15

```http
GET /api/travel/places/search?query=서울역&size=5
```

```json
{
  "query": "서울역",
  "candidates": [
    {
      "name": "서울역",
      "address": "서울 중구 한강대로 405",
      "lat": 37.55406888733184,
      "lng": 126.97070335253385,
      "category": "교통,수송 > 기차,철도 > 기차역 > KTX,SRT정차역"
    }
  ],
  "note": ""
}
```

키 없음·타임아웃·카카오 오류도 500이 아니라 아래처럼 온다.

```json
{"query": "서울역", "candidates": [], "note": "카카오 장소 검색에 실패해 빈 결과를 반환했습니다."}
```

빈 query나 `size=0/16`은 FastAPI 422다.

### 10.3 `GET /api/travel/places/reverse`

```http
GET /api/travel/places/reverse?lat=37.5547&lng=126.9707
```

```json
{
  "lat": 37.5547,
  "lng": 126.9707,
  "address": "서울특별시 용산구 남영동",
  "region": "서울특별시",
  "note": ""
}
```

외부 실패는 같은 좌표에 `address=""`, `region=""`, `note`를 채워 200으로 응답한다. 위도 범위 `-90..90`, 경도 범위 `-180..180` 밖이면 422다.

### 10.4 `POST /api/travel/route-plan` — 구조화 방식

```json
{
  "provider": "mock",
  "origin": {"name": "서울역", "lat": 37.5547, "lng": 126.9707},
  "destination": "부산",
  "start_date": "2026-08-22",
  "end_date": "2026-08-24",
  "start_time": "09:00:00",
  "end_time": "18:00:00",
  "message": "바다와 시장 중심"
}
```

`message`는 선택적 추가 요청이다. 구조화 방식의 필수 묶음은 `destination + start_date + end_date`다. `origin/start_time/end_time/provider`는 선택이다.

실응답 축약:

```json
{
  "provider": "mock",
  "model": "deterministic-travel-mock",
  "plan": {
    "destination": "부산",
    "nights": 2,
    "days": 3,
    "summary": "부산 핵심 명소와 맛집을 도는 교육용 2박 3일 루트입니다.",
    "landmarks": [
      {
        "name": "부산역",
        "summary": "여행의 시작점",
        "category": "교통",
        "day": 1,
        "visit_order": 1,
        "stay_minutes": 30,
        "tip": "짐 보관소를 활용하세요."
      }
    ],
    "foods": [
      {
        "name": "부산 전통시장 국밥",
        "cuisine": "한식",
        "signature_menu": "국밥",
        "price_range": "1만원 이하",
        "day": 1,
        "meal_time": "점심",
        "near_landmark": "부산역"
      }
    ]
  },
  "places": [
    {
      "name": "부산역",
      "kind": "landmark",
      "day": 1,
      "order": 1,
      "lat": 35.11520340622514,
      "lng": 129.04154985192403,
      "address": "부산 동구 중앙대로 206"
    }
  ],
  "not_found": [],
  "latency_ms": 0,
  "origin": {
    "name": "서울역",
    "kind": "origin",
    "day": 0,
    "order": 0,
    "lat": 37.5547,
    "lng": 126.9707,
    "address": "서울역"
  },
  "schedule": {
    "destination": "부산",
    "start_date": "2026-08-22",
    "end_date": "2026-08-24",
    "start_time": "09:00:00",
    "end_time": "18:00:00",
    "nights": 2,
    "days": 3
  }
}
```

실제 응답은 전체 `landmarks/foods/places` 배열을 포함한다. 지오코딩되지 않은 장소명만 `not_found`에 들어간다.

### 10.5 `POST /api/travel/route-plan` — 기존 message 하위호환

팀원이 먼저 만든 자연어 화면 계약을 계속 지원한다.

```json
{
  "message": "여수에 1박 2일 여행",
  "provider": "gemini"
}
```

응답의 `plan/places/not_found/provider/model/latency_ms`는 구조화 방식과 같고, 구조화 입력을 보내지 않았으므로 `origin`과 `schedule`은 `null`이다. 프런트가 목적지·숙박 수를 message에서 직접 파싱하지 않는다.

오류:

- message도 없고 완전한 구조화 묶음도 없음: 422
- 종료일이 시작일보다 빠르거나 30일 초과: 422
- Provider/LLM 생성 오류: 422 또는 502
- 카카오 지오코딩 키 없음·타임아웃·오류: HTTP 200, 카드용 `plan` 유지, `places`와 `not_found`로 부분 실패 표현

### 10.6 `GET /api/tools`

요청 body는 없다. 실응답 축약:

```json
{
  "tools": [
    {
      "name": "get_transit_route",
      "description": "출발지와 목적지 사이의 기차, 버스, 항공 대중교통을 조회합니다. 출발지·도착지 좌표와 출발 시각은 서버가 이미 알고 있으므로 넣지 않습니다.",
      "input_schema": {
        "additionalProperties": false,
        "properties": {
          "mode": {
            "default": "all",
            "enum": ["all", "train", "bus", "air"],
            "type": "string"
          }
        },
        "type": "object"
      }
    },
    {
      "name": "get_driving_route",
      "input_schema": {
        "additionalProperties": false,
        "properties": {
          "fuel_efficiency_kmpl": {"default": 12.0, "maximum": 40, "type": "number"},
          "fuel_price_per_liter": {"default": 1650, "maximum": 5000, "type": "integer"}
        },
        "type": "object"
      }
    }
  ],
  "note": "모든 Tool은 조회 전용이며 예약이나 결제를 실행하지 않습니다."
}
```

좌표가 LLM 노출 `input_schema`에 없는 것이 정상이다. 프런트는 목록을 하드코딩하지 않아도 되지만, 교육용 설명과 설정 상태를 보여줄 때 사용할 수 있다.

### 10.7 `POST /api/travel/transport`

```json
{
  "provider": "mock",
  "message": "KTX로 가면?",
  "origin": {"name": "서울역", "lat": 37.5547, "lng": 126.9707},
  "destination": {"name": "해운대", "lat": 35.1631, "lng": 129.1635},
  "departure_time": "2026-08-22T09:00:00",
  "tool_choice": "auto"
}
```

`message/origin/destination`은 필수다. `departure_time/provider`는 선택, `tool_choice`는 `auto|none|required`이며 기본 `auto`다.

KTX 질문 실응답 축약:

```json
{
  "provider": "mock",
  "question": "KTX로 가면?",
  "decision": {
    "provider": "mock",
    "model": "deterministic-transport-mock",
    "tool_name": "get_transit_route",
    "arguments": {
      "mode": "train",
      "origin_lat": 37.5547,
      "origin_lng": 126.9707,
      "dest_lat": 35.1631,
      "dest_lng": 129.1635,
      "departure_time": "2026-08-22T09:00:00"
    },
    "reason": "대중교통 이동 요청",
    "confidence": 0.95,
    "latency_ms": 0
  },
  "tool_result": {
    "success": true,
    "tool_name": "get_transit_route",
    "data": {
      "options": [
        {"type": "train", "label": "SRT", "from": "수서", "to": "부산", "minutes": 130, "fare_krw": 52200},
        {"type": "train", "label": "KTX", "from": "서울", "to": "부산", "minutes": 138, "fare_krw": 59800}
      ],
      "note": "도시간 검색은 역/터미널 기준 — 역↔목적지 시내 이동은 별도",
      "source": "odsay"
    },
    "error": null
  },
  "final_answer": "SRT 수서→부산 2시간 10분 52,200원 / KTX 서울→부산 2시간 18분 59,800원 / KTX 수서→부산 2시간 19분 52,900원",
  "trace": [
    {"stage": "tool_selection", "data": {}},
    {"stage": "argument_injection", "data": {"source": "request_body"}},
    {"stage": "tool_result", "data": {}},
    {"stage": "final_answer", "data": {}}
  ]
}
```

자가용 질문 실응답 핵심:

```json
{
  "decision": {
    "tool_name": "get_driving_route",
    "arguments": {
      "origin_lat": 37.5547,
      "origin_lng": 126.9707,
      "dest_lat": 35.1631,
      "dest_lng": 129.1635,
      "departure_time": "2026-08-22T09:00:00",
      "fuel_efficiency_kmpl": 12.0,
      "fuel_price_per_liter": 1650
    }
  },
  "tool_result": {
    "success": true,
    "tool_name": "get_driving_route",
    "data": {
      "distance_km": 408.7,
      "minutes": 311,
      "toll_krw": 22000,
      "fuel_krw": 56198,
      "taxi_krw": 378200,
      "total_krw": 78198,
      "assumptions": {"fuel_efficiency_kmpl": 12.0, "fuel_price_per_liter": 1650},
      "source": "kakao_mobility"
    },
    "error": null
  },
  "final_answer": "자가용 약 311분, 408.7km, 톨비 22,000원과 예상 유류비 56,198원으로 합계 78,198원입니다."
}
```

외부 키 없음·타임아웃·API 오류는 Tool data의 빈 결과와 `note`로 내려오거나 `success=false`가 되며, 엔드포인트는 안내 `final_answer`를 포함해 200으로 끝낸다. body 스키마 자체가 잘못되면 422다. `tool_choice="none"`이면 Tool을 실행하지 않았다는 안내가 정상 응답이다.

### 10.8 `POST /api/tools/run` — 프런트 본 화면에서는 호출하지 않음

학습·진단용 직접 실행 계약이다. 실제 화면은 반드시 `/api/travel/transport`를 호출해 Tool 선택과 서버 좌표 주입 trace를 보존한다.

```json
{
  "tool_name": "get_transit_route",
  "arguments": {
    "origin_lat": 37.5547,
    "origin_lng": 126.9707,
    "dest_lat": 35.1631,
    "dest_lng": 129.1635,
    "mode": "train"
  }
}
```

응답은 `{"success": true, "tool_name": "...", "data": ..., "error": null}` 형식이다. 미허용 이름은 `TOOL_NOT_ALLOWED`, 좌표 등 실행 인자 누락은 `TOOL_VALIDATION_ERROR`, 실행 예외는 `TOOL_EXECUTION_ERROR`이며 모두 HTTP 200의 `success=false`다.

## 11. API 클라이언트 변경 계약

현재 패턴을 유지한다. `core/api_client.py`는 공통 전송만, endpoint별 함수는 `clients/agent_client.py`에 둔다.

### `core/api_client.py`

GET query를 안전하게 전달하도록 기존 함수에 `params`만 추가한다.

```python
def request(
    method: str,
    path: str,
    json: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    ...
```

내부 `httpx.request(...)`에 `params=params`를 넘긴다. 기존 `json` 호출과 70초 timeout, `BackendAPIError` 동작은 유지한다.

### `clients/agent_client.py`

기존 `create_travel_route_plan(message, provider=None)`은 하위호환을 위해 유지하고 아래 함수를 추가한다.

```python
def get_travel_cities() -> dict: ...

def search_travel_places(query: str, size: int = 5) -> dict: ...

def reverse_travel_place(lat: float, lng: float) -> dict: ...

def create_structured_travel_route(
    origin: dict[str, object],
    destination: str,
    start_date: str,
    end_date: str,
    start_time: str,
    end_time: str,
    message: str = "",
    provider: str | None = None,
) -> dict: ...

def get_transport_tools() -> dict: ...

def complete_travel_transport(
    message: str,
    origin: dict[str, object],
    destination: dict[str, object],
    departure_time: str | None = None,
    provider: str | None = None,
    tool_choice: str = "auto",
) -> dict: ...
```

`provider`와 빈 `message` 같은 선택값은 불필요한 `null` 대신 필요할 때만 payload에 추가한다. 날짜·시간·datetime은 `isoformat()` 문자열로 보낸다.

## 12. 파일별 구현 범위와 현재 상태

| 파일 | 현재 상태 | 구현 PR에서 할 일 |
| --- | --- | --- |
| `frontend/app_pages/12_travel_route.py` | 팀원 로컬에 1차 버전 있음(PR #1 누락 — main push 필요). 아래 수정 가이드대로 확장 | 이 문서의 3택 입력, 카드, 지도, 교통 질문, trace를 완성 |
| `frontend/components/kakao_map.py` | landmark/food 지도 구현됨 | origin 마커와 좌표표 연동 추가, 기존 안전 직렬화·polyline 유지 |
| `frontend/clients/agent_client.py` | 기존 message 방식 함수 있음 | §11 endpoint 함수 추가, 기존 함수 유지 |
| `frontend/core/api_client.py` | JSON body만 지원 | `params` 선택 인자 추가 |
| `frontend/app.py` | `travel_route_page` 등록 완료 | `02. Prompt와 구조화 출력` expander의 `2-4. 여행 루트 추천` 위치 유지 |
| `requirements.txt` | `streamlit-js-eval` 없음 | 패키지 한 줄 추가, 기존 줄 삭제 금지 |
| `.env.example` | `BACKEND_API_URL`, `KAKAO_JS_KEY` 있음 | 기존 키 이름 유지, 실값 입력 금지 |

`app.py`의 등록 위치는 `structured_page` 다음, `image_page` 전이며 사이드바도 같은 2-4 위치다. 기존 01~11 페이지를 수정하지 않는다.

## 13. 환경변수와 실행

프런트가 사용하는 값:

```dotenv
BACKEND_API_URL=http://127.0.0.1:8000
KAKAO_JS_KEY=
```

백엔드의 `KAKAO_REST_KEY`, `ODSAY_KEY`, LLM 키는 브라우저나 Streamlit 상태에 노출하지 않는다. 실제 `.env`와 실키는 커밋하지 않는다.

로컬 실행:

```bash
cd mini_agent_02_structured_output/backend
../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

다른 터미널:

```bash
cd mini_agent_02_structured_output/frontend
../.venv/bin/python -m streamlit run app.py --server.port 8501
```

카카오 개발자 콘솔에는 실제 Streamlit origin(로컬이면 `http://localhost:8501`)을 등록한다. 브라우저 위치는 localhost/HTTPS에서만 기대한다.

## 14. 장애 표시 계약

- `not_found`가 있으면 `지도에서 찾지 못한 장소: ...` 경고를 지도 위에 표시한다.
- `places=[]`여도 여행 카드와 교통 질문은 유지한다.
- 장소 검색·역지오코딩의 `note`는 해당 입력 블록에서 안내한다.
- 지도 키/SDK 실패는 지도와 좌표표 구역에만 영향을 준다.
- `tool_result.success=false` 또는 Tool 미선택은 `final_answer`를 보여주고 경고 스타일을 추가한다.
- HTTP 422/502, 연결 실패, timeout은 기존 `BackendAPIError` 문구로 표시한다.
- 내부 예외, REST 키, 인증 헤더, 전체 요청 헤더는 화면에 노출하지 않는다.

## 15. 완료 기준 체크리스트

### 입력·요청

- [ ] 출발지 3택이 상호 배타적으로 동작함
- [ ] GPS 권한 거부 시 검색/도시 선택으로 유도함
- [ ] 검색 후보를 radio로 고른 뒤 명시적으로 확정함
- [ ] 도착 도시·날짜 range·출발/종료 시간이 구조화 payload로 전송됨
- [ ] 기존 message 전용 요청 함수가 깨지지 않음
- [ ] 서버 기본 Provider일 때 `provider` 필드를 생략함

### 여행 결과

- [ ] `schedule`과 `plan`으로 요약을 표시함
- [ ] 랜드마크와 음식이 일차별·순서별 카드로 표시됨
- [ ] origin/landmark/food 마커 색이 구분됨
- [ ] landmark만 일차별 polyline에 포함됨
- [ ] `not_found`와 `places=[]`에서도 카드가 유지됨
- [ ] 지도 실패 때 좌표표를 사용할 수 있음

### 교통 Tool

- [ ] “KTX로 가면?”이 `get_transit_route`, `mode=train`을 선택함
- [ ] “차로 가면?”이 `get_driving_route`를 선택함
- [ ] body의 좌표·출발 시각이 `argument_injection`에 표시됨
- [ ] `final_answer`를 먼저 보여주고 4단계 trace를 expander에 표시함
- [ ] Tool 실패가 HTTP 200이어도 `success=false`를 경고로 처리함
- [ ] 조회 전용이며 예약·결제를 하지 않는다고 표시함

### 회귀·안전

- [ ] `BACKEND_API_URL`과 `KAKAO_JS_KEY`만 프런트 환경에서 사용함
- [ ] REST/ODsay/LLM 키를 브라우저에 전달하지 않음
- [ ] 기존 Streamlit 01~11 페이지가 정상적으로 열림
- [ ] 좁은 화면에서 입력·카드·지도·trace가 가로로 넘치지 않음
- [ ] 임시 Mock 응답을 프런트 코드에 남기지 않음

## 16. 문서 상태

이 문서는 팀원이 작성한 기존 자연어 요청·카드·카카오맵·`not_found`·안전 직렬화 계약을 유지하고, 2단계의 구조화 입력·출발지 3택·교통 Tool Use 계약을 합친 최종 구현 기준이다. 백엔드 URL과 JSON 필드는 현재 구현 및 2026-08-20 실스모크 응답을 기준으로 확정했다.

## 17. 12_travel_route.py 수정 가이드 (팀원 1차 버전 기준)

팀원 로컬 186줄 파일을 연 뒤 아래 순서대로 바꾼다. 기존 `_render_day`, `_render_landmark`, `_render_food`는 그대로 재사용한다.

### 17.1 API 클라이언트와 import

**현재** (`12_travel_route.py` 3~9행, `clients/agent_client.py` 22~26행)
```python
from typing import Any
from clients.agent_client import create_travel_route_plan
def create_travel_route_plan(message: str, provider: str | None = None):
    payload = {"message": message}
```
→ **변경** (`core/api_client.request`에도 `params=None`을 추가하고 `httpx.request(..., params=params)`로 전달)
```python
# clients/agent_client.py
def get_travel_cities() -> dict:
    return request("GET", "/api/travel/cities")
def search_travel_places(query: str, size: int = 5) -> dict:
    return request("GET", "/api/travel/places/search", params={"query": query, "size": size})
def reverse_travel_place(lat: float, lng: float) -> dict:
    return request("GET", "/api/travel/places/reverse", params={"lat": lat, "lng": lng})
def create_travel_route_plan(message: str = "", provider: str | None = None, *,
    origin: dict[str, object] | None = None, destination: str | None = None,
    start_date: str | None = None, end_date: str | None = None,
    start_time: str | None = None, end_time: str | None = None) -> dict:
    payload = {"message": message} if message else {}
    for key, value in {"provider": provider, "origin": origin, "destination": destination,
        "start_date": start_date, "end_date": end_date, "start_time": start_time,
        "end_time": end_time}.items():
        if value is not None: payload[key] = value
    return request("POST", "/api/travel/route-plan", json=payload)
def ask_travel_transport(message: str, origin: dict[str, object],
    destination: dict[str, object], departure_time: str | None = None,
    provider: str | None = None) -> dict:
    payload = {"message": message, "origin": origin, "destination": destination, "tool_choice": "auto"}
    if departure_time: payload["departure_time"] = departure_time
    if provider: payload["provider"] = provider
    return request("POST", "/api/travel/transport", json=payload)
```
페이지 import에는 `from datetime import date, datetime, time, timedelta`, `from streamlit_js_eval import get_geolocation`과 위 5개 함수를 넣는다. 이유: GET query와 구조화 body를 한 클라이언트 계층에서 보내면서 기존 `create_travel_route_plan(message, provider)` 호출도 유지한다.
실스모크 요청/응답 JSON(§10.1~10.3 그대로):
```json
{}
{"cities":[{"name":"서울","lat":37.5663,"lng":126.9779},{"name":"부산","lat":35.1797,"lng":129.075},{"name":"제주","lat":33.4996,"lng":126.5312},{"name":"서귀포","lat":33.2541,"lng":126.5601}]}
{"query":"서울역","size":5}
{"query":"서울역","candidates":[{"name":"서울역","address":"서울 중구 한강대로 405","lat":37.55406888733184,"lng":126.97070335253385,"category":"교통,수송 > 기차,철도 > 기차역 > KTX,SRT정차역"}],"note":""}
{"lat":37.5547,"lng":126.9707}
{"lat":37.5547,"lng":126.9707,"address":"서울특별시 용산구 남영동","region":"서울특별시","note":""}
```

### 17.2 입력 블록과 호출부

**현재** (`12_travel_route.py` 154~177행): 자유 `text_area`를 `normalized_message`로 만든 뒤 `create_travel_route_plan(normalized_message, provider)`를 호출한다.
→ **변경** (143행 아래 입력부 전체 교체)
```python
if "travel-origin" not in st.session_state: st.session_state["travel-origin"] = None
if "travel-candidates" not in st.session_state: st.session_state["travel-candidates"] = []
cities = _items(get_travel_cities().get("cities"))
origin_mode = st.radio("출발지 선택", ["브라우저 위치", "장소 검색", "도시 선택"], horizontal=True)
if origin_mode == "브라우저 위치" and st.button("📍 현재 위치 가져오기"):
    coords = (get_geolocation() or {}).get("coords") or {}
    lat, lng = coords.get("latitude"), coords.get("longitude")
    if lat is None or lng is None: st.warning("위치를 가져오지 못했어요. 다른 방식을 이용해 주세요.")
    else:
        reverse = reverse_travel_place(float(lat), float(lng))
        st.session_state["travel-origin"] = {"name": reverse.get("address") or f"{lat:.4f},{lng:.4f}", "lat": float(lat), "lng": float(lng)}
elif origin_mode == "장소 검색":
    query = st.text_input("주소 또는 장소명")
    if st.button("장소 검색") and query.strip():
        found = search_travel_places(query.strip(), 5)
        st.session_state["travel-candidates"] = _items(found.get("candidates"))
        if not st.session_state["travel-candidates"]: st.info(found.get("note") or "검색 결과가 없습니다.")
    candidates = st.session_state["travel-candidates"]
    if candidates:
        picked = st.radio("검색 후보", candidates, format_func=lambda x: f"{x['name']} · {x.get('address','')} · {x.get('category','')}")
        if st.button("이 출발지로 확정"): st.session_state["travel-origin"] = {k: picked[k] for k in ("name", "lat", "lng")}
else:
    origin_city = st.selectbox("출발 도시", cities, format_func=lambda x: x["name"])
    st.session_state["travel-origin"] = {k: origin_city[k] for k in ("name", "lat", "lng")}
origin = st.session_state["travel-origin"]
if origin: st.success(f"✅ {origin['name']} ({origin['lat']:.4f}, {origin['lng']:.4f})")
destination = st.selectbox("도착 도시", cities, format_func=lambda x: x["name"])
dates = st.date_input("여행 기간", value=(date.today() + timedelta(days=1), date.today() + timedelta(days=3)))
start_time, end_time = st.time_input("출발 시간", time(9)), st.time_input("종료 시간", time(18))
message = st.text_input("추가 요청", placeholder="바다와 시장 중심")
selected_provider = st.selectbox("Provider", list(provider_options))
if st.button("여행 루트 만들기", type="primary"):
    if not origin or len(dates) != 2: st.warning("출발지와 시작·종료일을 확정해 주세요.")
    elif dates[1] < dates[0] or (dates[1] - dates[0]).days > 29: st.warning("기간은 종료일이 늦고 최대 30일이어야 합니다.")
    else:
        response = create_travel_route_plan(message.strip(), provider_options[selected_provider], origin=origin,
            destination=destination["name"], start_date=dates[0].isoformat(), end_date=dates[1].isoformat(),
            start_time=start_time.isoformat(), end_time=end_time.isoformat())
        st.session_state[RESULT_STATE_KEY], st.session_state["travel-context"] = response, {
            "origin": origin, "destination": destination, "departure_time": datetime.combine(dates[0], start_time).isoformat(),
            "provider": provider_options[selected_provider]}
        st.session_state.pop("travel-transport-result", None)
```
이유: 출발지를 세 방식 중 하나로 확정하고 일정·시간·추가 요청을 별도 구조화 필드로 보낸다(`BackendAPIError`의 기존 `try/except`는 이 블록 주위에 유지).
실스모크 요청/응답 JSON(§10.4의 핵심 필드 그대로):
```json
{"provider":"mock","origin":{"name":"서울역","lat":37.5547,"lng":126.9707},"destination":"부산","start_date":"2026-08-22","end_date":"2026-08-24","start_time":"09:00:00","end_time":"18:00:00","message":"바다와 시장 중심"}
{"provider":"mock","model":"deterministic-travel-mock","plan":{"destination":"부산","nights":2,"days":3,"summary":"부산 핵심 명소와 맛집을 도는 교육용 2박 3일 루트입니다.","landmarks":[{"name":"부산역","summary":"여행의 시작점","category":"교통","day":1,"visit_order":1,"stay_minutes":30,"tip":"짐 보관소를 활용하세요."}],"foods":[{"name":"부산 전통시장 국밥","cuisine":"한식","signature_menu":"국밥","price_range":"1만원 이하","day":1,"meal_time":"점심","near_landmark":"부산역"}]},"places":[{"name":"부산역","kind":"landmark","day":1,"order":1,"lat":35.11520340622514,"lng":129.04154985192403,"address":"부산 동구 중앙대로 206"}],"not_found":[],"latency_ms":0,"origin":{"name":"서울역","kind":"origin","day":0,"order":0,"lat":37.5547,"lng":126.9707,"address":"서울역"},"schedule":{"destination":"부산","start_date":"2026-08-22","end_date":"2026-08-24","start_time":"09:00:00","end_time":"18:00:00","nights":2,"days":3}}
```
### 17.3 결과 요약과 origin 지도 마커

**현재** (`_render_result` 100~105, 117~120, 138~140행): 기간은 `plan`만 읽고 `render_kakao_map(places)`에는 origin을 넣지 않는다. `kakao_map.normalize_places` 77행은 `{"landmark", "food"}`만 통과시킨다.
→ **변경** (`_render_result`에서 기존 헬퍼와 탭은 유지)
```python
schedule = result.get("schedule") if isinstance(result.get("schedule"), dict) else {}
days = min(max(_integer(schedule.get("days"), _integer(plan.get("days"), 1)), 1), 30)
nights = max(_integer(schedule.get("nights"), _integer(plan.get("nights"), days - 1)), 0)
destination_column.metric("목적지", _text(schedule.get("destination") or plan.get("destination")))
duration_column.metric("여행 기간", f"{nights}박 {days}일")
if schedule.get("start_time") and schedule.get("end_time"):
    st.caption(f"선택 시간: {schedule['start_time']} ~ {schedule['end_time']}")
map_places = ([result["origin"]] if isinstance(result.get("origin"), dict) else []) + places
render_kakao_map(map_places)
```
```python
# components/kakao_map.py
if kind not in {"origin", "landmark", "food"} or not name: continue
"day": max(_integer(item.get("day"), 0), 0),
# _MAP_HTML에도 .origin { background: #16a34a; }와 범례를 추가한다.
const color = kind === "origin" ? "#16a34a" : kind === "food" ? "#ef4444" : "#2563eb";
const label = kind === "origin" ? "O" : kind === "food" ? "F" : "L";
const typeLabel = place.kind === "origin" ? "출발지" : place.kind === "food" ? "음식점" : "랜드마크";
```
이유: 구조화 응답의 일정과 출발지를 보이되 origin은 기존 랜드마크 polyline에서 계속 제외한다. 사용 JSON은 바로 위 §17.2 응답의 `schedule`, `origin`, `places`와 동일하다.
### 17.4 지도 아래 교통편 질문과 trace

**현재** (`_render_result` 138~140행): `render_kakao_map(places)` 호출 뒤 함수가 끝난다.

→ **변경** (`render_kakao_map(map_places)` 바로 아래)

```python
context = st.session_state.get("travel-context") or {}
landmark = next((p for p in places if p.get("kind") == "landmark"), None)
transport_destination = ({"name": landmark["name"], "lat": landmark["lat"], "lng": landmark["lng"]}
    if landmark else context.get("destination"))
if not context or not transport_destination: return
st.subheader("교통편 질문")
examples = st.columns(3)
for column, example in zip(examples, ["KTX로 가면?", "고속버스로 가면?", "차로 가면?"]):
    if column.button(example): st.session_state["travel-transport-question"] = example
question = st.text_input("교통편 질문", placeholder="KTX로 가면?", key="travel-transport-question")
if st.button("교통편 알아보기") and question.strip():
    st.session_state["travel-transport-result"] = ask_travel_transport(question.strip(), context["origin"],
        transport_destination, context["departure_time"], context.get("provider"))
transport = st.session_state.get("travel-transport-result")
if isinstance(transport, dict):
    st.success(_text(transport.get("final_answer"), "교통편 답변이 없습니다."))
    tool_result = transport.get("tool_result")
    if not isinstance(tool_result, dict) or not tool_result.get("success"):
        st.warning("교통 조회 Tool이 실행되지 않았거나 조회에 실패했습니다.")
    with st.expander("Tool 실행 과정"):
        labels = {"tool_selection": "1. Tool 선택", "argument_injection": "2. 서버 인자 주입·검증",
            "tool_result": "3. 조회 실행", "final_answer": "4. 답변"}
        details = {"tool_selection": transport.get("decision"), "argument_injection": (transport.get("decision") or {}).get("arguments"),
            "tool_result": tool_result, "final_answer": transport.get("final_answer")}
        for item in transport.get("trace") or []:
            st.markdown(f"**{labels.get(item.get('stage'), item.get('stage'))}**")
            st.json(item.get("data") or details.get(item.get("stage")) or {})
        st.caption("좌표·출발 시각은 request body에서 서버가 강제 주입하며, 조회 전용이라 예약·결제하지 않습니다.")
```
이유: 첫 추천 랜드마크 좌표를 우선 목적지로 쓰고 없으면 선택 도시로 폴백하며, 수업 05/03의 4단계 trace와 fail-soft 실패를 그대로 보여준다.
실스모크 요청/응답 JSON(§10.7 그대로):

```json
{"provider":"mock","message":"KTX로 가면?","origin":{"name":"서울역","lat":37.5547,"lng":126.9707},"destination":{"name":"해운대","lat":35.1631,"lng":129.1635},"departure_time":"2026-08-22T09:00:00","tool_choice":"auto"}
{"provider":"mock","question":"KTX로 가면?","decision":{"provider":"mock","model":"deterministic-transport-mock","tool_name":"get_transit_route","arguments":{"mode":"train","origin_lat":37.5547,"origin_lng":126.9707,"dest_lat":35.1631,"dest_lng":129.1635,"departure_time":"2026-08-22T09:00:00"},"reason":"대중교통 이동 요청","confidence":0.95,"latency_ms":0},"tool_result":{"success":true,"tool_name":"get_transit_route","data":{"options":[{"type":"train","label":"SRT","from":"수서","to":"부산","minutes":130,"fare_krw":52200},{"type":"train","label":"KTX","from":"서울","to":"부산","minutes":138,"fare_krw":59800}],"note":"도시간 검색은 역/터미널 기준 — 역↔목적지 시내 이동은 별도","source":"odsay"},"error":null},"final_answer":"SRT 수서→부산 2시간 10분 52,200원 / KTX 서울→부산 2시간 18분 59,800원 / KTX 수서→부산 2시간 19분 52,900원","trace":[{"stage":"tool_selection","data":{}},{"stage":"argument_injection","data":{"source":"request_body"}},{"stage":"tool_result","data":{}},{"stage":"final_answer","data":{}}]}
{"provider":"mock","message":"차로 가면?","origin":{"name":"서울역","lat":37.5547,"lng":126.9707},"destination":{"name":"해운대","lat":35.1631,"lng":129.1635},"departure_time":"2026-08-22T09:00:00","tool_choice":"auto"}
{"decision":{"tool_name":"get_driving_route","arguments":{"origin_lat":37.5547,"origin_lng":126.9707,"dest_lat":35.1631,"dest_lng":129.1635,"departure_time":"2026-08-22T09:00:00","fuel_efficiency_kmpl":12.0,"fuel_price_per_liter":1650}},"tool_result":{"success":true,"tool_name":"get_driving_route","data":{"distance_km":408.7,"minutes":311,"toll_krw":22000,"fuel_krw":56198,"taxi_krw":378200,"total_krw":78198,"assumptions":{"fuel_efficiency_kmpl":12.0,"fuel_price_per_liter":1650},"source":"kakao_mobility"},"error":null},"final_answer":"자가용 약 311분, 408.7km, 톨비 22,000원과 예상 유류비 56,198원으로 합계 78,198원입니다."}
```

### 17.5 의존성

**현재** (`requirements.txt`): `streamlit-js-eval`이 없다. → **변경**: 팀원이 기존 줄을 지우지 말고 `streamlit-js-eval` 한 줄을 추가한다.
이유: 브라우저 위치 권한과 좌표를 Streamlit 백엔드로 전달하는 데 필요하다. 이 항목은 HTTP API 요청/응답이 없으며, 설치 후 GPS 결과가 있으면 §17.1의 reverse 실스모크 JSON 계약으로 처리한다.
