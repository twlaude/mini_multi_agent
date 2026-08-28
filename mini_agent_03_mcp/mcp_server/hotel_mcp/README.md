# Hotel MCP

여기어때 웹 데이터를 이용해 국내 숙소를 검색하고 객실 옵션과 결제 직전 링크를 제공하는 교육용 MCP 서버입니다.

## 제공 Tool

- `search_accommodations`
- `get_room_options`
- `make_checkout_link`

## 실행

```powershell
pip install -r requirements.txt
Copy-Item .env.example .env
python hotel_server.py
```

기본 주소는 `http://127.0.0.1:8030/mcp`입니다. API 키가 없으므로 `.env`를 만들지 않아도 기본 설정으로 실행할 수 있습니다.

## 구조

교재 `backend/app` 관례(`core · schemas · services`)를 따르되, MCP 서버라 `routers` 대신 `tools`, 외부 사이트 호출은 `clients`로 분리했습니다.

```
hotel_mcp/
├── hotel_server.py            진입점 — FastMCP 생성 + tools 4개 register (로직 없음)
├── app/
│   ├── core/
│   │   ├── config.py          .env → HotelSettings (host/port/타임아웃/여기어때 URL)
│   │   └── deps.py            프로세스당 하나 공유하는 client (FastAPI Depends 역할)
│   ├── schemas/
│   │   ├── accommodation.py   Hotel / RoomOption 모델
│   │   └── constants.py       RENT/STAY, SORT_TYPES, CATEGORY_CODES, SortType/Category
│   ├── clients/
│   │   ├── base.py            AccommodationClient 인터페이스 + SearchPage (services 는 이것만 안다)
│   │   └── yeogi/             여기어때 구현체
│   │       ├── client.py      HTTP 호출 (buildId 캐시·404 재시도, 표준 라이브러리만) + category 코드 변환
│   │       └── parser.py      JSON/HTML → 모델 변환 (네트워크 없음)
│   ├── services/
│   │   ├── dates.py           날짜 검증·기본값 (공용)
│   │   ├── search_service.py  Tool 1 로직
│   │   ├── room_service.py    Tool 2 로직
│   │   └── checkout_service.py Tool 3 로직 (결제 링크)
│   └── tools/                 (= routers) MCP Tool/Resource 등록만
│       ├── search.py          search_accommodations
│       ├── rooms.py           get_room_options
│       ├── checkout.py        make_checkout_link
│       └── resources.py       yeogi://sort-types, yeogi://today
└── tests/
    ├── conftest.py            샘플 응답 + 가짜 client
    ├── test_parser.py
    └── test_services.py
```

요청 흐름: `tools` → `services` → `clients`(HTTP) → `clients/parser` → `schemas`

- 새 Tool 추가: `services/`에 함수 + `tools/`에 파일 하나 만들고 `hotel_server.py`에 `xxx.register(mcp)` 한 줄
- 데이터 소스 교체(다른 숙소 사이트): `clients/base.py`의 `AccommodationClient`를 구현한 패키지를 `clients/` 아래 추가하고 `core/deps.py`의 `get_client`만 변경 — `services`·`tools`·`schemas`·`tests`는 그대로 (tests/conftest.py 의 FakeClient 가 최소 구현 예시)
- 테스트: `python -m pytest -q tests` (네트워크 없이 services·parser 검증)

여기어때 공식 API가 아닌 웹 데이터 엔드포인트를 이용하므로 사이트 구조가 변경되면 동작하지 않을 수 있습니다.
