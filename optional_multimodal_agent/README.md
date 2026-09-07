# 멀티모달 Agent 실습

사진·텍스트·음성을 입력받아 MCP Tool, RAG, 업무 DB를 사용하는 두 가지 Python AI Agent 예제. Frontend는 Streamlit, Backend는 FastAPI, LangGraph는 안 씀.

| Agent     | 입력                           | 사용하는 정보                          | 출력                     |
| --------- | ------------------------------ | -------------------------------------- | ------------------------ |
| 제품 안내 | 제품 사진과 텍스트·음성 질문   | 제품 설명서, 호환 액세서리, 가격, 재고 | 사용법·출처·재고·음성    |
| 시설 안내 | 안내문 사진과 텍스트·음성 질문 | 참가 안내, 시설 규정, 일정, 잔여 정원  | 참가 조건·일정·출처·음성 |

제품·시설·재고·안내문은 모두 가상 실습 자료. 실제 예약이나 결제는 안 함.

> **맥북 기준 메모 (2026-09-07)**: 원본 README는 Windows PowerShell + 전용 pgvector 컨테이너(5433) 기준이었음. 맥북은 5433을 homebrew postgresql@17이 쓰고 있고, [infra/README.md](../infra/README.md) 메모대로 컨테이너를 새로 안 만들기 때문에 **기존 `pg` 컨테이너(5432)에 `multimodal_agent_db`만 추가**해서 쓴다. 아래 절차는 전부 그 기준.

## 0. 빠른 시작 (이미 세팅된 상태)

```bash
docker start pg ollama redis
cd ~/class_personal_projects/mini_multi_agent/optional_multimodal_agent
.venv/bin/python -m scripts.check_services   # postgres, redis OK 면 됨 (mcp·backend는 아래 4절에서 띄움)
```

그 다음 4절 "실행"으로.

## 1. 준비 (최초 1회)

Python 3.11 이상 + OpenAI API 키. 맥북엔 pyenv 3.12.7이 있고 다른 챕터도 같은 걸로 `.venv`를 만들었다.

```bash
cd ~/class_personal_projects/mini_multi_agent/optional_multimodal_agent
~/.pyenv/versions/3.12.7/bin/python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

`.env`에서 `OPENAI_API_KEY`만 채운다. 상위 폴더 `../.env`에 있는 키 그대로. 나머지 기본값은 이 맥북 기준으로 이미 맞춰져 있다.

```dotenv
DATABASE_URL=postgresql://agent_user:agent_password@127.0.0.1:5432/multimodal_agent_db
REDIS_URL=redis://127.0.0.1:6379/0
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_EMBEDDING_MODEL=embeddinggemma
EMBEDDING_DIMENSIONS=768
```

OpenAI는 Agent 판단, 이미지 분석, STT, TTS에 쓰고 RAG 임베딩은 Ollama `embeddinggemma`.

## 2. Docker 서비스 (기존 컨테이너 재사용)

맥북엔 이미 공용 컨테이너 3개가 있다. 새로 만들지 말고 켜기만 한다.

| 컨테이너 | 역할                | 포트  |
| -------- | ------------------- | ----- |
| `pg`     | pgvector/pg16       | 5432  |
| `ollama` | embeddinggemma 등   | 11434 |
| `redis`  | 작업 큐·상태        | 6379  |

```bash
open -a Docker            # Docker Desktop 꺼져 있으면
docker start pg ollama redis
docker ps                 # 3개 Up 확인
```

Ollama에 `embeddinggemma`가 없으면 한 번만:

```bash
docker exec ollama ollama pull embeddinggemma
```

### 프로젝트 DB 만들기 (최초 1회)

`agent_user`는 슈퍼유저가 아니라 `vector` 확장을 못 만든다. DB 생성과 확장은 슈퍼유저 `parking`으로 한다.

```bash
docker exec pg psql -U parking -d postgres -c "CREATE DATABASE multimodal_agent_db OWNER agent_user"
docker exec pg psql -U parking -d multimodal_agent_db -c "CREATE EXTENSION IF NOT EXISTS vector"
```

## 3. 데이터 준비 (최초 1회)

```bash
# 프로젝트 테이블 생성 (sql/01~04 순서대로)
.venv/bin/python -m scripts.setup_database

# 제품·재고·시설·프로그램 가상 데이터 입력
.venv/bin/python -m scripts.seed_database

# data/rag Markdown → embeddinggemma → pgvector 적재
.venv/bin/python -m scripts.ingest_knowledge
```

일정 Seed는 실행일 이후 첫 토요일부터 4주를 만든다. 기준일 지정도 가능.

```bash
.venv/bin/python -m scripts.seed_database --base-date 2026-09-07
```

Seed를 다시 돌려도 기존 재고와 회차는 안 덮어쓴다.

확인:

```bash
docker exec pg psql -U agent_user -d multimodal_agent_db -Atc \
  "select (select count(*) from multimodal_products),(select count(*) from multimodal_program_sessions),(select count(*) from multimodal_knowledge_chunks)"
# 10|24|44 나오면 정상
```

## 4. 실행

터미널(또는 tmux 창) 4개. 각 하위 폴더에서 바로 실행하도록 되어 있다.

```bash
# 터미널 1: MCP Tool Server (:8020)
cd ~/class_personal_projects/mini_multi_agent/optional_multimodal_agent/mcp_server
../.venv/bin/python main.py
```

```bash
# 터미널 2: FastAPI Backend (:8000)
cd ~/class_personal_projects/mini_multi_agent/optional_multimodal_agent/backend
../.venv/bin/python -m uvicorn app.main:app --reload
```

```bash
# 터미널 3: Redis 작업을 처리하는 Agent Worker
cd ~/class_personal_projects/mini_multi_agent/optional_multimodal_agent/backend
../.venv/bin/python workers/agent_worker.py
```

```bash
# 터미널 4: Streamlit Frontend (:8501)
cd ~/class_personal_projects/mini_multi_agent/optional_multimodal_agent/frontend
../.venv/bin/python -m streamlit run app.py
```

브라우저에서 `http://localhost:8501`. 카메라 권한을 허용하거나 `data/samples/`의 이미지를 업로드한다. 음성 질문은 최대 120초 WAV, 이미지는 JPEG·PNG·WEBP.

전체 상태 확인 (4개 다 띄운 뒤):

```bash
cd ~/class_personal_projects/mini_multi_agent/optional_multimodal_agent
.venv/bin/python -m scripts.check_services
```

Worker가 안 떠 있으면 작업은 `queued`에서 멈춰 있다.

## 4-1. 재부팅 후 / 자주 막히는 것

- 컨테이너 셋 다 `Exited`면 `docker start pg ollama redis`.
- `permission denied to create extension "vector"` → 2절의 `parking`으로 확장 생성 안 한 것.
- `relation "multimodal_products" does not exist` → `setup_database`를 먼저 안 돌린 것.
- `mcp FAIL` / `backend FAIL` → 터미널 1·2가 안 떠 있는 것. postgres·redis만 OK면 데이터 세팅은 정상.
- 5433 포트는 homebrew postgresql@17 자리. 이 프로젝트는 안 쓴다.

## 5. 전체 흐름

```text
Streamlit에서 사진·질문 입력
        ↓
FastAPI가 파일 저장 및 작업 등록
        ↓
Redis 작업 큐 → Python Worker가 Agent 실행
        ↓
MCP Tool Server
├─ 이미지 분석·STT·TTS
├─ 업무 데이터 조회 → PostgreSQL
└─ RAG 검색 → Ollama embeddinggemma + pgvector
        ↓
Worker가 Redis에 진행 상태 저장
        ↓
FastAPI SSE → Streamlit 화면 갱신
```

실행 상태는 `queued → running → completed / needs_input / failed` 순서로 바뀝니다. 진행 이벤트에는 Tool 시작·완료·실패만 기록합니다. TTS가 실패해도 텍스트 답변은 유지됩니다.

## 6. 디렉터리와 코드 읽는 순서

```text
optional_multimodal_agent/
├─ frontend/          Streamlit 화면
├─ backend/           FastAPI, Agent, Worker, Redis·SSE
│  ├─ app/            API와 Agent 실행 코드
│  └─ workers/        Redis 작업 처리 프로세스
├─ mcp_server/        이미지·음성·RAG·DB Tool
├─ sql/               테이블 생성과 가상 데이터
├─ data/rag/          RAG Markdown 문서
├─ data/samples/      촬영·업로드용 이미지
├─ scripts/           DB 준비, RAG 적재, 서비스 확인
└─ tests/             자동 테스트
```

1. `frontend/app_pages/01_product_agent.py`: 사진과 질문 입력
2. `backend/app/routers/runs.py`: 작업 등록과 SSE API
3. `backend/app/core/`: Backend 설정과 미디어 저장·검증
4. `backend/workers/agent_worker.py`: Redis 작업 처리
5. `backend/app/agents/product_agent.py`: Agent 지침과 허용 Tool
6. `backend/app/agents/runner.py`: Tool 호출과 답변 생성
7. `mcp_server/core/`: MCP 설정과 미디어 읽기
8. `mcp_server/tools/product_tools.py`: MCP Tool
9. `mcp_server/database/product_queries.py`: DB 조회
10. `backend/app/stores/`: Redis 상태·이벤트·작업 큐

## 7. Frontend와 Backend

Streamlit은 `st.camera_input`, `st.audio_input`, `st.audio`를 사용합니다. Python 코드가 Backend SSE를 수신하므로 별도 HTML이나 JavaScript는 없습니다. 새로고침하면 실행 ID와 마지막 이벤트 ID를 이용해 진행 상태를 복원합니다.

각 프로그램은 자신의 `core/config.py`에서 필요한 환경변수만 읽습니다. Backend가 업로드 파일을 저장하고 MCP Server는 같은 `MEDIA_STORAGE_DIR`에서 파일을 읽거나 생성 음성을 저장합니다.

FastAPI 문서: `http://127.0.0.1:8000/docs`

| API                          | 기능                        |
| ---------------------------- | --------------------------- |
| `POST /api/media/image`      | 이미지 업로드               |
| `POST /api/media/audio`      | WAV 음성 업로드             |
| `GET /api/media/{id}`        | 이미지·생성 음성 조회       |
| `POST /api/runs`             | Agent 작업 등록             |
| `GET /api/runs/{id}`         | 실행 상태와 결과 조회       |
| `GET /api/runs/{id}/events`  | 진행 상황 SSE 수신          |
| `POST /api/runs/{id}/input`  | 추가 질문 또는 새 사진 전달 |
| `POST /api/runs/{id}/speech` | 최종 답변 음성 재생성       |

Worker가 실행되지 않으면 작업은 `queued` 상태로 기다립니다.

## 8. MCP Tool

MCP Server 주소는 `http://127.0.0.1:8020/mcp`입니다.

| Tool                         | 역할                               |
| ---------------------------- | ---------------------------------- |
| `analyze_scene`              | 제품 사진과 라벨 분석              |
| `read_document`              | 안내문 사진과 코드 분석            |
| `transcribe_audio`           | 녹음을 질문 텍스트로 변환          |
| `synthesize_speech`          | 최종 답변을 MP3로 생성             |
| `find_products`              | 제품 후보 조회                     |
| `get_compatible_accessories` | 호환 액세서리 조회                 |
| `get_product_availability`   | 가격과 매장별 재고 조회            |
| `find_programs`              | 프로그램과 시설 확인               |
| `get_program_sessions`       | 회차와 잔여 정원 조회              |
| `search_product_manuals`     | 제품 설명서 RAG 검색               |
| `search_facility_guides`     | 프로그램 안내와 시설 규정 RAG 검색 |

Agent는 임의 SQL이나 로컬 파일 경로를 Tool에 전달하지 않습니다. DB Tool은 정해진 인자만 받고 읽기 전용 SQL을 실행합니다.

## 9. PostgreSQL

| 영역     | 테이블                                                                                          | 내용                    |
| -------- | ----------------------------------------------------------------------------------------------- | ----------------------- |
| 제품     | `multimodal_products`, `multimodal_product_compatibility`                                       | 제품과 호환 관계        |
| 재고     | `multimodal_stores`, `multimodal_inventory`                                                     | 매장과 재고             |
| 시설     | `multimodal_facilities`, `multimodal_programs`                                                  | 시설과 프로그램         |
| 일정     | `multimodal_program_sessions`                                                                   | 회차와 잔여 정원        |
| RAG      | `multimodal_knowledge_documents`, `multimodal_knowledge_chunks`                                 | 문서와 768차원 벡터     |
| RAG 연결 | `multimodal_product_documents`, `multimodal_facility_documents`, `multimodal_program_documents` | 업무 데이터와 문서 연결 |

`sql/01_extensions.sql`부터 `sql/04_knowledge_tables.sql`까지 번호 순서로 실행합니다. 별도 일반 인덱스와 벡터 인덱스는 사용하지 않습니다.

## 10. RAG 문서 추가

별도 manifest 파일은 없습니다. 적재 스크립트가 Markdown 파일을 자동으로 찾습니다.

```text
data/rag/
├─ products/       제품 설명서
└─ facilities/     프로그램 안내와 시설 규정
```

| 파일                    | 연결 대상          |
| ----------------------- | ------------------ |
| `products/MM-K100.md`   | 제품 `MM-K100`     |
| `facilities/PG-YOGA.md` | 프로그램 `PG-YOGA` |
| `facilities/F01.md`     | 시설 `F01`         |

파일 이름은 DB의 대상 ID와 같아야 합니다. Markdown 첫 줄의 `# 제목`은 Agent가 보여주는 출처 제목입니다. 문서를 추가하거나 수정한 뒤 다시 적재합니다.

```bash
.venv/bin/python -m scripts.ingest_knowledge
```

## 11. 실습 시나리오

| 샘플 이미지                    | 질문                    | 확인할 동작                         |
| ------------------------------ | ----------------------- | ----------------------------------- |
| `product_labels/MM-K100.png`   | 사용법·호환 필터·재고   | 제품 확인, 매뉴얼 출처, AC-K10 재고 |
| `product_labels/MM-A300.png`   | 필터 주의사항·재고      | 물세척 금지와 AC-A30 품절           |
| `product_labels/unclear.png`   | 사용법                  | 모델을 추측하지 않고 추가 입력 요청 |
| `facility_notices/PG-YOGA.png` | 초보 참가·향후 4주 자리 | 준비물, 첫 회차 마감, DB 정보 확인  |
| `facility_notices/PG-DRAW.png` | 일정·준비물             | 두 번째 회차 취소 확인              |
| `product_labels/MM-K100.png`   | 해외 전압 호환          | 근거가 없음을 알리고 추측하지 않음  |

`data/samples/scenarios.json`은 위 내용을 구조화한 수동 실습 자료이며 Agent가 실행 중 읽지는 않습니다.

## 12. 테스트

```bash
.venv/bin/python -m pytest -q
```

테스트는 미디어 검증, Redis 상태 전환, SSE 재연결, Agent Tool 호출, API 입력과 Streamlit 화면을 확인합니다. 테스트 대역을 사용하므로 OpenAI API 비용은 발생하지 않습니다.

## 실행 범위

- Redis 상태와 이벤트는 기본 24시간 보관하며 키에 `mm:` 접두사를 사용합니다.
- 이미지와 음성은 UUID 파일명으로 `storage`에 저장하고 Redis에는 파일 ID만 보관합니다.
- 추가 입력은 이전 답변을 포함한 새 실행이며 장기 대화 메모리는 아닙니다.
- 스마트폰 등 다른 장치에서 카메라를 사용하려면 HTTPS 환경이 필요합니다.
- 인증 없는 로컬 학습용이므로 외부 공개 서비스로 사용하지 않습니다.
