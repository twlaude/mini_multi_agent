# 공통 Docker 환경

> **태웅 맥북 메모 (2026-08-25)**: 맥북엔 이미 공용 컨테이너 `pg`(pgvector, :5432 — DB `agent_db`/`parking`/`lostfound`), `ollama`(:11434 — llama3.1:8b, llama3.2), `redis`(:6379)가 있다. 아래 `docker compose up`은 **실행하지 말고** `docker start pg ollama redis`로 켠다. 새 프로젝트는 컨테이너를 새로 만들지 않고 `docker exec pg psql -U parking -c "create database <이름>"`로 DB만 추가.

모든 누적 단계가 같은 Ollama, PostgreSQL/pgvector, Redis 컨테이너를 사용합니다. 단계마다 컨테이너를 새로 만들지 않습니다.

## 시작

```powershell
cd C:\mini_agent_st\infra
Copy-Item .env.example .env
docker compose up -d
docker compose ps
docker exec mini-agent-ollama ollama pull llama3.2
docker exec mini-agent-ollama ollama pull embeddinggemma
```

`llama3.2`는 답변을 만드는 채팅 모델이고 `embeddinggemma`는 문장을 검색용 숫자 벡터로 바꾸는 Embedding 모델입니다.

## 주소

| 서비스 | 주소 |
| --- | --- |
| Ollama | `http://127.0.0.1:11434` |
| PostgreSQL/pgvector | `127.0.0.1:5432` |
| Redis | `redis://127.0.0.1:6379/0` |

첫 단계는 Ollama만 사용합니다. PostgreSQL/pgvector는 Mini Agent 04, Redis는 Mini Agent 05부터 본격적으로 연결합니다.

- Mini Agent 04: `documents`에 RAG Chunk와 Vector 저장
- Mini Agent 05: Redis에 TTL 단기 상태, `user_memories`와 `conversation_messages`에 장기 데이터 저장

## 기존 PostgreSQL Volume 주의

`postgres/init.sql`은 PostgreSQL Volume을 처음 만들 때만 자동 실행됩니다. 기존 학습 데이터를 유지한다면 Volume을 삭제하지 말고 `postgres/init.sql`의 `documents` 생성 구문만 DB에 직접 실행합니다.

컨테이너가 실행 중일 때 다음 명령으로 안전하게 스키마만 적용할 수 있습니다.

```powershell
Get-Content -Raw .\postgres\init.sql |
    docker exec -i mini-agent-postgres psql -U agent_user -d agent_db
```

## 종료

```powershell
docker compose stop
```

`docker compose down -v`는 학습 데이터를 삭제하므로 일반 종료에는 사용하지 않습니다.
