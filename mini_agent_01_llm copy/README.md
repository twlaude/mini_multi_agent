# Mini Agent 01 · LLM 판단에서 서비스 연결까지

`01_llm-to-agent`의 단위 Python 예제를 FastAPI Endpoint와 Streamlit 메뉴로
하나씩 연결합니다. 첫 단계에서는 로그인과 Agent Workflow를 넣지 않습니다.

```text
Python 판단 함수
→ FastAPI
→ Streamlit 메뉴
→ Mock
→ Gemini
→ OpenAI GPT
→ Docker Ollama/Llama
→ 이미지 분석
→ 음성 생성
```

## 이번 단계에서 구현

- LLM·Workflow·Agent 비교
- 여행 요청 분류
- 낮은 confidence와 추가 질문
- Mock Provider로 연결 확인
- Gemini·GPT·Ollama/Llama 선택
- 동일 Prompt의 모델·응답 시간·실패 비교
- GPT 이미지 분석과 업로드 검증
- 여행 안내문 MP3 합성 음성 생성

## 아직 구현하지 않음

- Structured Output
- LangChain
- Tool
- RAG와 Memory
- Agent Workflow와 LangGraph
- 로그인

## 실행 (macOS, Host에서 직접)

환경 변수는 서비스별로 나뉘어 있다. 루트에는 `.env`가 없다.

```text
backend/.env   → LLM Provider·API Key·모델·Ollama 주소 (backend/.env.example 참고)
frontend/.env  → BACKEND_API_URL (frontend/.env.example 참고)
```

```bash
cd ~/class_personal_projects/mini_multi_agent/"mini_agent_01_llm copy"
source .venv/bin/activate
test -f backend/.env  || cp backend/.env.example backend/.env
test -f frontend/.env || cp frontend/.env.example frontend/.env
```

터미널 1:

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

터미널 2:

```bash
streamlit run frontend/app.py
```

Ollama는 맥북의 기존 `ollama` 컨테이너(`docker start ollama`)를 쓴다. Cloud Provider는
`backend/.env`에 API Key와 모델을 설정한 경우에만 호출한다.

## Docker Compose로 실행

Backend·Frontend를 **각각 별도 Image**로 빌드하고 Compose 하나로 묶는다. 환경 변수는 각
서비스의 `.env`를 `env_file`로 주입하고, 컨테이너 안에서만 달라지는 주소는 `compose.yml`의
`environment`가 덮어쓴다 (`environment` > `env_file`).

```text
backend/Dockerfile  + backend/requirements.txt  + backend/.env   → Image: mini-agent-01-backend
frontend/Dockerfile + frontend/requirements.txt + frontend/.env  → Image: mini-agent-01-frontend
compose.yml          두 Image를 빌드·연결 (frontend → http://backend:8000, backend → host.docker.internal:11434 Ollama)
compose.release.yml  Docker Hub Image만 pull 해서 실행 (빌드 없음)
push_images.sh       Docker Hub에 amd64+arm64 멀티 아키텍처로 빌드·푸시
```

```bash
docker compose config --quiet
docker compose up --build -d
docker compose ps
curl -s http://127.0.0.1:8000/health
open http://127.0.0.1:8501
docker compose down
```

코드나 `.env`를 고친 뒤에는 `docker compose up -d --build --force-recreate` 로 다시 만든다
(`.env`만 고쳤으면 `--build` 없이 `--force-recreate`만).

### Docker Hub에 올리고 받기

```bash
docker login                     # Docker Hub 계정 (twlaude)
bash push_images.sh 1.0.0        # buildx 멀티 아키텍처 빌드 + push
```

수신자는 `compose.release.yml` + `backend/.env.example` + `frontend/.env.example` 만 받아서
`.env` 두 개를 만들고 실행한다.

```bash
docker compose -f compose.release.yml pull
docker compose -f compose.release.yml up -d
docker compose -f compose.release.yml ps
```

## 확인 순서

1. LLM·Workflow·Agent 메뉴에서 두 판단 결과를 비교합니다.
2. 여행 요청 분류에서 `confidence`와 추가 질문을 확인합니다.
3. 환경 상태에서 Backend와 Provider 설정을 확인합니다.
4. 기본 Provider인 Mock으로 Frontend·Backend 연결을 확인합니다.
5. 이전 과정에서 사용한 Gemini를 연결합니다.
6. GPT와 Ollama/Llama를 추가해 같은 질문을 비교합니다.
7. Ollama Container를 중지하고 실패가 비교 결과에 남는지 확인합니다.
8. 이미지 분석에서 업로드 형식과 구조화된 결과를 확인합니다.
9. 음성 생성에서 안내문을 MP3로 변환하고 합성 음성 고지를 확인합니다.

Provider 비교는 `Gemini → GPT → Ollama/Llama` 순서로 진행합니다. Cloud Provider는
호출량과 비용을 확인하고, Ollama는 Docker와 모델 준비 상태를 먼저 확인합니다.

이미지 분석과 음성 생성은 01 단원의 `1-5`, `1-6` 메뉴에서 진행합니다.
