# Mini Agent 03 · MCP

`mini_agent_03_tool`의 여행 Tool을 MCP Server로 분리한 작은 실전 프로젝트입니다.
FastAPI Backend는 Tool 함수를 직접 import하지 않고 MCP Client를 통해 Tool을 발견하고
호출합니다.

교재의 mock 서버(`travel_server.py`·`policy_stdio_server.py`) 대신 **5팀이 만든
실제 MCP Server 3개**를 `mcp_server/` 아래에 두고 Backend에 등록했습니다.

```text
Streamlit :8501
  → FastAPI Backend :8000
    → hotel     MCP Server :8030/mcp  여기어때 숙소 검색·객실·결제 링크 (Streamable HTTP)
    → tour_spot MCP Server :8040/mcp  한국관광공사 관광지 검색           (Streamable HTTP)
    → weather   MCP Server :8050/mcp  기상청 현재 날씨·주간 예보         (Streamable HTTP)
    → OpenAI Responses API가 한 번에 Tool 하나를 선택
      → Tool 결과를 돌려주고 필요한 만큼 반복
```

세 MCP Server는 Backend와 독립된 프로세스와 포트에서 실행합니다. Frontend는 MCP
Server를 직접 호출하지 않습니다. 사용자의 요청은 항상 Agent Backend를 거치며, GPT가
Tool을 제안하고 Backend가 MCP 호출·결과 전달을 담당합니다.

## 폴더 구조

```text
mini_agent_03_mcp/
├── backend/app/
│   ├── main.py            FastAPI 엔드포인트
│   ├── mcp_client.py      MCP_SERVERS 등록표 + Session 생성 (hotel / tour_spot / weather)
│   ├── agent.py           Tool prefix·라우팅과 순차 Agent Loop
│   └── schemas.py
├── frontend/app.py        Streamlit
├── mcp_server/
│   ├── hotel_mcp/         형 — 여기어때 (hotel_server.py, app/ core·schemas·clients·services·tools, tests/)
│   ├── tour_spot_mcp/     오현님 — 한국관광공사 TourAPI (tour_spot_server.py, tour_spot/)
│   ├── weather_mcp/       인혜님 — 기상청 (weather_server.py 단일 파일)
│   ├── travel_server.py   교재 mock (미등록, 참고용)
│   └── policy_stdio_server.py 교재 stdio mock (미등록, 참고용)
└── .env                   Backend가 읽는 MCP URL + OpenAI 키
```

각 MCP Server 폴더는 제출물 그대로이며 **자기 폴더의 `.env`** 를 읽습니다
(`hotel_mcp/.env`, `tour_spot_mcp/.env`, `weather_mcp/.env`). 프로젝트 루트 `.env`는
Backend·Frontend 전용입니다.

## 제공 Tool (총 6개)

| Server | Tool | 설명 |
| --- | --- | --- |
| hotel | `search_accommodations` | 키워드·날짜·카테고리로 숙소 검색 (가격 필터 없음 — AI가 판별) |
| hotel | `get_room_options` | 숙소 id → 객실별 대실/숙박 옵션·재고 |
| hotel | `make_checkout_link` | 숙소 id + 객실 id → 결제 직전 URL (결제는 안 함) |
| tour_spot | `search_tour_spots` | 국내 지역명 → 관광지 목록 |
| weather | `get_current_weather` | 고정 지역(.env) 현재 날씨 |
| weather | `get_weekly_forecast` | 고정 지역 7일 예보 |

Resource: `yeogi://sort-types`, `yeogi://today` (hotel)

## 제공 API

- `GET /health`: Backend 상태
- `GET /api/mcp/status`: MCP Server 3개 연결 상태 (하나라도 죽으면 503)
- `GET /api/mcp/tools`: Tool 발견
- `GET /api/mcp/resources`: Resource 발견
- `GET /api/mcp/resource?server=hotel&uri=yeogi://today`: Resource 읽기
- `POST /api/mcp/run`: 질문 → Tool 선택 → MCP 호출 → 답변 Trace

## 실행 순서 (macOS, 로컬 전부)

터미널 5개. 모두 이 폴더(`mini_agent_03_mcp`)에서 시작합니다.

```bash
cd ~/class_personal_projects/mini_multi_agent/mini_agent_03_mcp
source .venv/bin/activate
```

```bash
# 1  hotel MCP  :8030
python mcp_server/hotel_mcp/hotel_server.py

# 2  tour_spot MCP  :8040
python mcp_server/tour_spot_mcp/tour_spot_server.py

# 3  weather MCP  :8050
python mcp_server/weather_mcp/weather_server.py

# 4  Backend  :8000
uvicorn backend.app.main:app --reload --port 8000

# 5  Frontend  :8501
streamlit run frontend/app.py --server.port 8501
```

확인:

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/api/mcp/status          # status=connected, tool_count=6
curl -s http://127.0.0.1:8000/api/mcp/tools | python -m json.tool
curl -s -X POST http://127.0.0.1:8000/api/mcp/run -H 'Content-Type: application/json' \
  -d '{"question":"서울 현재 날씨랑 부산 관광지 3곳, 부산 호텔 15만원 이하 3곳 추천해줘"}'
```

브라우저: `http://127.0.0.1:8501` / Swagger `http://127.0.0.1:8000/docs`

종료는 Frontend → Backend → MCP Server 순으로 각 터미널에서 `Ctrl+C`.

## 환경변수

루트 `.env` (Backend·Frontend):

```env
BACKEND_API_URL=http://127.0.0.1:8000
HOTEL_MCP_URL=http://127.0.0.1:8030/mcp
TOUR_SPOT_MCP_URL=http://127.0.0.1:8040/mcp
WEATHER_MCP_URL=http://127.0.0.1:8050/mcp
OPENAI_API_KEY=발급받은_API_KEY
OPENAI_MODEL=gpt-4.1-mini
```

MCP Server별 `.env` (각 폴더의 `.env.example` 참고):

- `hotel_mcp/.env`: 키 불필요. `HOTEL_MCP_PORT=8030`
- `tour_spot_mcp/.env`: `TOUR_API_SERVICE_KEY` = 공공데이터포털 키 (**한국관광공사 KorService2 활용신청 필요**), `TOUR_SPOT_MCP_PORT=8040` (hotel과 충돌 피하려고 8030→8040)
- `weather_mcp/.env`: `KMA_SERVICE_KEY` = 공공데이터포털 키 (**기상청 단기예보 + 중기예보 두 API 활용신청 필요**), `KMA_NX/NY`·`REG_ID`는 서울 기본값

공공데이터포털 키는 계정당 하나지만 API마다 활용신청을 따로 해야 합니다. 신청 안 된
API를 부르면 `SERVICE_KEY_IS_NOT_REGISTERED_ERROR`가 나며, 서버는 죽지 않고 Tool
결과에 `ok: false`로 돌려줍니다.

## 팀원 서버를 LAN으로 쓸 때

강의실에서 팀원 PC의 서버를 붙일 땐 루트 `.env`의 URL만 바꿉니다.

```env
TOUR_SPOT_MCP_URL=http://192.100.200.223:8030/mcp
WEATHER_MCP_URL=http://192.100.200.170:8050/mcp
```

## 비교 포인트

| `mini_agent_03_tool` | `mini_agent_03_mcp` |
| --- | --- |
| Backend가 Tool 함수를 직접 import | Backend는 MCP Client만 사용 |
| Tool 목록이 Agent 코드에 고정 | `tools/list`로 서버에서 발견 |
| Python 함수 직접 호출 | `tools/call` 프로토콜 호출 |
| 앱 내부 Context | URI 기반 MCP Resource |

Backend는 세 MCP Server에서 발견한 Tool Schema에 Server prefix(`hotel__`,
`tour_spot__`, `weather__`)를 붙여 OpenAI Responses API에 전달합니다.
`parallel_tool_calls=False`이므로 GPT는 한 Round에 Tool 하나를 제안하고, Function
Call 없이 답변할 때까지 Agent Loop를 반복합니다.
