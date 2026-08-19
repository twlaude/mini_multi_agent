# plan.md — 여행 루트 추천 Frontend (2-4)

> 마스터 문서: `../TRAVEL_ROUTE_MASTER.md` (스키마 계약·지도 API 결정은 거기가 SSOT)

## 목표

`app_pages/12_travel_route.py` 페이지 하나:
여행 요청 입력 → 백엔드 `/api/travel/route-plan` 호출 → 랜드마크/맛집 카드 + 카카오맵(마커+일차별 경로선) 표시.

## 설계

### 페이지 (`app_pages/12_travel_route.py`)

| 구역 | 내용 |
| --- | --- |
| 입력 | `st.text_input` 자유 입력 (예: "부산에 2박 3일 여행") + provider `selectbox` (기존 09 페이지 패턴) + 실행 버튼 |
| 요약 | destination · N박 M일 · summary 한 줄 |
| 일차별 탭 | `st.tabs(["1일차", ...])` — 탭 안에 방문 순서대로 랜드마크 카드(설명/체류시간/팁) + 맛집 카드(대표메뉴/가격대/시간대) |
| 지도 | 전체 동선 카카오맵 임베드 (아래) |
| 실패 표시 | `not_found` 있으면 `st.warning("지도에 못 찍은 곳: ...")` |

### 지도 임베드 (`core/kakao_map.py` 신규)

- `render_route_map(places, js_key) -> str` : 카카오맵 JS SDK HTML 문자열 생성 → `st.components.v1.html(html, height=500)`
- 마커: landmark=파랑, food=주황. 클릭 시 인포윈도우(이름)
- 경로선: 일차별로 `visit_order` 순 polyline, 일차마다 색 다르게
- 중심/줌: 좌표 bounds로 자동 (`map.setBounds`)
- JS 키는 `.env`의 `KAKAO_JS_KEY` → `st.secrets`/`os.environ` 경유 (하드코딩 금지)
- 폴백: JS 키 미설정이면 지도 대신 `st.info("KAKAO_JS_KEY 설정 필요")` + 좌표 테이블 표시

### 클라이언트 (`core/api_client.py`에 추가)

- `create_travel_route(message, provider) -> dict` — 기존 함수들과 동일 패턴 (`POST /api/travel/route-plan`, timeout은 LLM+지오코딩 감안해 60초)

### 메뉴 등록 (`app.py`)

- `st.Page("app_pages/12_travel_route.py", title="여행 루트 추천")`
- 사이드바 "02. Prompt와 구조화 출력" expander에 `2-4. 여행 루트 추천`으로 추가

## 구현 단계

1. [ ] `core/api_client.py`: `create_travel_route()` 추가
2. [ ] `core/kakao_map.py`: 지도 HTML 생성 함수
3. [ ] `app_pages/12_travel_route.py`: 페이지 작성
4. [ ] `app.py`: 페이지 + 사이드바 등록
5. [ ] 카카오 개발자 콘솔에 `http://localhost:8501` 도메인 등록 확인 (지도 안 뜨면 1순위 의심)
6. [ ] 실기 테스트: "부산에 2박 3일" → 카드 + 지도 마커/경로선 확인

## 완료 기준

- 자유 입력 → 일차별 랜드마크/맛집 카드 표시
- 지도에 마커(색 구분) + 일차별 경로선 렌더
- 지오코딩 실패 장소는 경고로만 표시, 페이지는 정상 동작
- JS 키 없어도 페이지가 죽지 않음 (폴백 동작)
