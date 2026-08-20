# plan.md — 여행 루트 추천 Frontend (2-4)

> 마스터 문서: `../TRAVEL_ROUTE_MASTER.md`
> 백엔드 계약: `../backend/plan.md`
> 프런트는 고정된 API 계약을 소비하며 지오코딩을 직접 수행하지 않는다.

## 1. 담당 목표

기존 Streamlit 앱에 여행 질문 페이지를 추가한다. 사용자가 자연어 요청을 보내면 백엔드의 `plan`을 여행 카드로 보여주고 `places`를 카카오 지도 마커와 일차별 랜드마크 경로선으로 표시한다. `places`가 비어도 카드 UI는 정상적으로 유지한다.

## 2. 확정 API 사용법

### 요청

```http
POST /api/travel/route-plan
```

```json
{
  "message": "여수에 1박 2일 여행",
  "provider": "gemini"
}
```

- 질문은 `message`로 보낸다.
- Provider 기본 선택은 `서버 기본값`으로 두고 이 경우 요청에서 `provider`를 생략한다.
- 선택 가능한 Provider를 노출한다면 기존 목록인 `mock`, `gemini`, `openai`, `ollama`를 사용한다.
- 목적지, 숙박 수, 여행 일수, 장소 개수를 프런트에서 추출하거나 별도 전송하지 않는다.
- 기존 `frontend/core/api_client.py`의 타임아웃은 70초이므로 최소 60초 권장 조건을 이미 충족한다.

### 응답 소비

```text
response
├─ provider / model / latency_ms
├─ plan
│  ├─ destination / nights / days / summary
│  ├─ landmarks[]
│  └─ foods[]
├─ places[]
└─ not_found[]
```

- 여행 카드 데이터는 `plan`에서 읽는다.
- 지도 데이터는 `places`에서만 읽는다.
- 경고는 `not_found`에서 읽는다.
- `plan.landmarks`와 `places`를 배열 위치로 결합하지 않는다. 필요할 때는 `name`과 `kind`를 기준으로 찾는다.

## 3. 화면 구성

### 입력 영역

- 제목: `🗺️ 여행 루트 추천`
- 안내: 자연어로 목적지와 기간 입력
- 기본 예시: `부산에 2박 3일 여행 가고 싶어`
- `st.text_area` 질문 입력
- Provider 선택: 서버 기본값을 기본으로 제공
- `여행 루트 만들기` 버튼
- 공백 질문은 요청하지 않고 안내 표시

### 요청 상태

- 요청 시작부터 완료까지 `st.spinner` 표시
- 안내 문구: `여행 장소와 지도 좌표를 찾고 있어요. 약 10초 정도 걸릴 수 있습니다.`
- 중복 클릭으로 같은 요청이 연속 실행되지 않게 버튼 흐름을 단순화
- 성공 결과는 `st.session_state`에 보관해 Streamlit 재실행에도 유지

### 여행 요약

- 목적지: `plan.destination`
- 기간: `plan.nights`박 `plan.days`일
- 여행 컨셉: `plan.summary`
- Provider, 모델, 처리 시간은 작은 보조 정보로 표시

### 일차별 카드

`1`부터 `plan.days`까지 일차별 탭 또는 구역으로 표시한다.

랜드마크 카드:

- `visit_order` 순으로 정렬
- 장소명, 한 줄 설명, 카테고리
- 권장 체류 시간
- 방문 팁

음식 카드:

- `meal_time` 순서(아침 → 점심 → 저녁)로 정렬
- 상호명, 음식 종류, 대표 메뉴, 가격대
- 가까운 랜드마크

`places`가 비어 있어도 위 카드들은 `plan`만으로 모두 표시한다.

## 4. 카카오 지도 규칙

### SDK

- `st.components.v1.html`로 카카오 Maps JavaScript SDK를 임베드한다.
- `.env`의 `KAKAO_JS_KEY`를 사용한다.
- 프로젝트 루트 `.env`는 `python-dotenv`로 읽는다.
- 카카오 개발자 콘솔에 `http://localhost:8501` 등 실제 Streamlit 도메인을 등록한다.
- `KAKAO_REST_KEY`는 프런트에서 읽거나 브라우저로 전달하지 않는다.

### 마커

- `places[]`의 모든 항목을 마커로 표시한다.
- `kind="landmark"`와 `kind="food"`를 색상 또는 라벨로 구분한다.
- 마커 정보창: 장소명, 종류, 일차, 주소
- 음식점은 `order=0`이므로 방문 순서 문구를 표시하지 않는다.
- `places=[]`이면 지도 대신 `지도에서 확인할 수 있는 좌표가 없습니다.` 안내를 표시한다.

### 경로선

1. `kind="landmark"`만 선택한다.
2. `day`별로 그룹화한다.
3. 각 그룹을 `order` 오름차순으로 정렬한다.
4. 일차별로 서로 다른 색상의 polyline을 그린다.
5. `kind="food"`는 경로선에 포함하지 않는다.
6. 하루의 랜드마크가 1개뿐이면 경로선 없이 마커만 표시한다.

### 지도 범위

- 유효한 모든 마커가 보이도록 bounds를 자동 조정한다.
- 마커가 하나면 해당 장소를 중심으로 적절한 확대 수준을 사용한다.
- 위도·경도 값이 숫자가 아니거나 범위를 벗어나면 해당 항목만 제외한다.
- 제외로 인해 화면 전체가 실패하지 않게 한다.

## 5. `not_found` 및 장애 처리

- `not_found`가 하나 이상이면 지도 위에 경고 영역을 표시한다.
- 예: `지도에서 찾지 못한 장소: A, B`
- `not_found` 장소는 지도 마커나 경로선에 사용하지 않는다.
- `places=[]`이면서 `not_found`가 있어도 `plan` 카드 UI는 정상 표시한다.
- 카카오 JavaScript 키 누락이나 SDK 로드 실패는 지도 영역의 안내로 제한하고 여행 카드까지 숨기지 않는다.
- 백엔드 연결 실패, HTTP 422/502, 시간 초과는 기존 `BackendAPIError` 형식으로 표시한다.
- 내부 예외, REST 키, 전체 인증 문자열은 화면에 노출하지 않는다.

## 6. 안전한 지도 데이터 전달

- Python의 장소 목록을 JSON으로 직렬화한 뒤 HTML 컴포넌트에 전달한다.
- 사용자/LLM 문자열을 JavaScript 코드에 직접 이어 붙이지 않는다.
- `</script>` 삽입을 막도록 `<`, `>`, `&` 문자를 안전하게 이스케이프한다.
- 지도 렌더 함수는 원본 응답을 변경하지 않고 검증된 지도 항목만 별도 생성한다.

## 7. 파일 변경 계획

### 신규 파일

| 파일 | 내용 |
|---|---|
| `frontend/app_pages/12_travel_route.py` | 질문 입력, 스피너, 카드, 경고, 지도 페이지 |
| `frontend/components/kakao_map.py` | 지도 HTML, 마커, 일차별 polyline 렌더링 |
| `frontend/components/__init__.py` | 프런트 컴포넌트 패키지 |

### 기존 파일 최소 수정

| 파일 | 변경 |
|---|---|
| `frontend/clients/agent_client.py` | `create_travel_route_plan(message, provider=None)` 함수 1개 추가 |
| `frontend/app.py` | 새 페이지 등록과 사이드바 링크 추가 |
| `.env.example` | `KAKAO_JS_KEY=` 이름과 도메인 등록 안내 추가. 백엔드 키 항목은 덮어쓰지 않음 |

### 수정하지 않을 파일

- 기존 `frontend/app_pages/01~11` 페이지
- `frontend/core/api_client.py` — 기존 70초 타임아웃 사용
- 백엔드 구현 파일 및 백엔드 계약
- 실제 `.env` 값 — 키 입력은 사용자가 수행

공유 파일인 `.env.example`을 수정할 때는 백엔드 담당자의 `KAKAO_REST_KEY` 항목을 유지하고 `KAKAO_JS_KEY`만 추가한다.

## 8. API 클라이언트 함수 초안

```python
def create_travel_route_plan(message: str, provider: str | None = None):
    payload = {"message": message}
    if provider:
        payload["provider"] = provider
    return request("POST", "/api/travel/route-plan", json=payload)
```

서버 기본 Provider를 사용할 때 `provider: null`을 보내지 않고 필드 자체를 생략한다.

## 9. 구현 순서

1. 백엔드 변경사항이 현재 작업 폴더에 병합됐는지 확인
2. `/docs`에서 요청 및 실제 응답 필드 확인
3. API 클라이언트 함수 추가
4. 카드 중심 페이지 구현
5. `not_found`와 `places=[]` 상태 구현
6. 카카오 지도 마커 구현
7. 일차별 랜드마크 경로선 구현
8. `frontend/app.py`에 페이지 연결
9. `.env.example`에 JS 키 설정 안내 추가
10. 정상·부분 실패·전체 지오코딩 실패를 통합 확인

백엔드가 아직 작업 폴더에 병합되지 않았다면 고정 응답 예시로 UI를 먼저 확인할 수 있지만, 임시 Mock 데이터는 최종 코드에 남기지 않는다.

## 10. 검증 시나리오

### 정상 응답

- [ ] 질문과 선택 Provider가 정확히 전달됨
- [ ] 스피너가 응답 전까지 표시됨
- [ ] 여행 요약과 일차별 카드가 표시됨
- [ ] 모든 `places`가 마커로 표시됨
- [ ] 명소만 일차별·순서별 경로선으로 연결됨
- [ ] 음식점은 마커만 표시됨

### 일부 지오코딩 실패

- [ ] 성공 장소는 지도에 표시됨
- [ ] `not_found`는 경고로 표시됨
- [ ] 실패 장소를 경로선에 포함하지 않음
- [ ] 전체 카드 UI는 정상 표시됨

### 카카오 지오코딩 전체 실패

- [ ] HTTP 200 응답을 성공 결과로 처리함
- [ ] `places=[]` 지도 빈 상태를 표시함
- [ ] 전체 `not_found` 경고를 표시함
- [ ] `plan` 카드 UI는 정상 표시됨

### 지도 SDK 실패

- [ ] `KAKAO_JS_KEY` 누락 안내가 표시됨
- [ ] 도메인/SDK 오류가 지도 영역에서 안내됨
- [ ] 지도 실패와 관계없이 카드가 표시됨

### 회귀 확인

- [ ] 기존 Streamlit 01~11 페이지가 정상적으로 열림
- [ ] 기존 API 호출 화면이 영향을 받지 않음
- [ ] 좁은 화면에서도 지도와 카드가 가로로 넘치지 않음

## 11. 완료 기준

- 자연어 여행 질문을 고정 API로 보낼 수 있다.
- 약 10초 처리 동안 사용자가 진행 상태를 확인할 수 있다.
- `plan`의 모든 필드가 읽기 쉬운 카드로 표시된다.
- `places` 마커와 일차별 랜드마크 경로선이 정확하다.
- 음식점은 경로선에 포함되지 않는다.
- `not_found`와 `places=[]` 상황에서도 카드 UI가 유지된다.
- 기존 프런트 기능을 깨지 않는다.

## 12. 문서 상태

이 문서는 고정된 `TRAVEL_ROUTE_MASTER.md`와 `backend/plan.md`를 기준으로 작성한 프런트 담당 구현 계획이다. API 계약 변경이 발생하면 구현 전에 팀 합의와 마스터 문서 갱신이 먼저 필요하다.
