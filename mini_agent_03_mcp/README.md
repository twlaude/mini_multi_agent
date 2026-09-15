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
├── backend/.env           Backend 전용 (MCP URL + OpenAI 키)
├── frontend/.env          Frontend 전용 (BACKEND_API_URL)
├── postgres/init.sql      PostgreSQL 첫 생성 때 실행되는 스키마 (교재 infra/postgres/init.sql 과 동일)
├── compose.yml            Image 5개 빌드·연결 + PostgreSQL/pgvector
└── compose.release.yml    Docker Hub Image만 pull + PostgreSQL/pgvector
```

각 서비스는 **자기 폴더의 `.env`** 만 읽습니다 (`backend/.env`, `frontend/.env`,
`hotel_mcp/.env`, `tour_spot_mcp/.env`, `weather_mcp/.env`). 프로젝트 루트에는 `.env`가 없습니다.

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

루트에는 `.env`가 없다. 서비스마다 자기 `.env`만 가진다 (각 폴더의 `.env.example` 참고).

```text
backend/.env                      OPENAI_API_KEY·OPENAI_MODEL + MCP 3개 주소(Host 실행용 127.0.0.1)
frontend/.env                     BACKEND_API_URL
mcp_server/hotel_mcp/.env         키 불필요. HOTEL_MCP_PORT=8030 (+ OPENAI_API_KEY: 정책 임베딩용)
mcp_server/tour_spot_mcp/.env     TOUR_API_SERVICE_KEY (한국관광공사 KorService2 활용신청), TOUR_SPOT_MCP_PORT=8040
mcp_server/weather_mcp/.env       KMA_SERVICE_KEY (기상청 단기+중기예보 활용신청), KMA_NX/NY·REG_ID 서울 기본값
```

공공데이터포털 키는 계정당 하나지만 API마다 활용신청을 따로 해야 한다. 신청 안 된
API를 부르면 `SERVICE_KEY_IS_NOT_REGISTERED_ERROR`가 나며, 서버는 죽지 않고 Tool
결과에 `ok: false`로 돌려준다.

## Docker Compose로 실행 (Image 5개 + PostgreSQL)

서비스 5개를 **각각 별도 Image**로 빌드하고 PostgreSQL/pgvector까지 `compose.yml` 하나로 묶는다.

```text
mcp_server/hotel_mcp/Dockerfile      → mini-agent-03-hotel-mcp      :8030
mcp_server/tour_spot_mcp/Dockerfile  → mini-agent-03-tour-spot-mcp  :8040
mcp_server/weather_mcp/Dockerfile    → mini-agent-03-weather-mcp    :8050
backend/Dockerfile                   → mini-agent-03-backend        :8000  (MCP 3개 healthy 후 시작)
frontend/Dockerfile                  → mini-agent-03-frontend       :8501  (backend healthy 후 시작)
pgvector/pgvector:pg16 (공식 Image)  → postgres                     :5432  (hotel-mcp는 이게 healthy 된 뒤 시작)
```

`postgres`는 볼륨 `postgres_data`에 데이터를 두고, 볼륨을 **처음 만들 때만** `postgres/init.sql`로
`vector` 확장과 `documents` 테이블을 만든다. 호텔 규정 청크는 첫 조회 때 hotel-mcp가 알아서 색인하니
빈 DB로 시작해도 된다. 호스트에서 직접 보려면 `docker compose exec postgres psql -U agent_user -d agent_db`
(또는 `127.0.0.1:5433` — 맥북 공용 `pg`가 5432를 쓰고 있어 기본값을 5433으로 뒀다. `POSTGRES_PORT`로 변경).

환경 변수는 각 서비스 `.env`를 `env_file`로 주입하고, **컨테이너 안에서만 달라지는 값**은
`compose.yml`의 `environment`가 덮어쓴다 (`environment` > `env_file`).

| 덮어쓰는 값 | Host 실행 (.env) | Compose 안 |
| --- | --- | --- |
| MCP 바인딩 호스트 `*_MCP_HOST` | `127.0.0.1` | `0.0.0.0` (다른 컨테이너가 접속) |
| Backend → MCP 주소 `*_MCP_URL` | `http://127.0.0.1:80x0/mcp` | `http://hotel-mcp:8030/mcp` 등 서비스 이름 |
| Frontend → Backend `BACKEND_API_URL` | `http://127.0.0.1:8000` | `http://backend:8000` |
| hotel → PostgreSQL `DATABASE_URL` | `127.0.0.1:5432` | `postgres:5432` (Compose 안 `postgres` 서비스) |

```bash
cd ~/class_personal_projects/mini_multi_agent/mini_agent_03_mcp
docker compose config --quiet
docker compose up --build -d
docker compose ps
curl -s http://127.0.0.1:8000/api/mcp/status     # status=connected, tool_count=8
open http://127.0.0.1:8501
docker compose down        # 컨테이너만 정리, PG 데이터(postgres_data 볼륨)는 남는다
docker compose down -v     # 볼륨까지 삭제 (색인한 호텔 규정도 지워진다)
```

### Docker Hub에 올리고 받기

```bash
docker login
bash push_images.sh 1.0.0        # 5개 Image를 amd64+arm64로 빌드 + push
```

수신자는 `compose.release.yml` + `postgres/init.sql` + 각 서비스 폴더의 `.env.example` 을 받아
`.env` 5개를 만들고 빌드 없이 실행한다 (PostgreSQL은 공식 `pgvector/pgvector:pg16` Image라 따로 올리지 않는다).

```bash
docker compose -f compose.release.yml pull
docker compose -f compose.release.yml up -d
```

## 팀원 서버를 LAN으로 쓸 때

강의실에서 팀원 PC의 서버를 붙일 땐 `backend/.env`의 URL만 바꿉니다.

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
