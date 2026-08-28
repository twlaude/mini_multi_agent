# 호텔 규정 RAG 데이터 번들 사용법 (Windows)

이 번들은 여기어때 호텔 상세 페이지의 규정 텍스트를 `documents` 테이블에 적재하기 위한 교육용 데이터다. Windows PowerShell에서 아래 명령을 실행한다. 기본 DB 주소는 교재 환경과 같은 `127.0.0.1:5433/agent_db`다.

## 공통 준비

PowerShell에서 번들 폴더로 이동하고 DB 적재 패키지를 설치한다.

```powershell
Set-Location "$HOME\Downloads\hotel_policy_bundle_0828"
py -m pip install "psycopg[binary]" pgvector
```

PostgreSQL DB가 실행 중이어야 한다. 로더는 `vector` 확장과 `documents` 테이블이 없으면 교재의 `infra/postgres/init.sql`과 같은 DDL로 생성한다. 해당 DB 사용자에게 확장·테이블 생성 권한이 없으면, 관리자 계정으로 `init.sql`을 먼저 적용한다.

## A. text-embedding-3-small을 그대로 쓰는 경우

벡터 포함본을 사용하면 OpenAI 호출과 임베딩 비용 없이 바로 적재할 수 있다.

```powershell
py .\load_hotel_policies.py `
  --input .\hotel_policy_embeddings_openai_text-embedding-3-small.jsonl `
  --embed none `
  --replace
```

기본 포트가 아닌 DB에는 접속 URL을 명시한다.

```powershell
py .\load_hotel_policies.py `
  --input .\hotel_policy_embeddings_openai_text-embedding-3-small.jsonl `
  --database-url "postgresql://agent_user:agent_password@127.0.0.1:5432/agent_db" `
  --collection hotel_policy `
  --embed none `
  --replace
```

`--embed none`인데 어느 행에든 `embedding`이 없으면 로더가 적재 전에 오류와 해결 방법을 안내한다.

## B. 다른 임베딩으로 다시 만드는 경우

한 컬렉션 안에는 같은 provider·model·차원의 벡터만 넣어야 한다. 기존 벡터와 섞이지 않도록 텍스트본과 `--replace`를 함께 사용한다.

### Ollama embeddinggemma

Ollama를 실행하고 모델을 준비한 뒤 `httpx`를 설치한다.

```powershell
ollama pull embeddinggemma
py -m pip install httpx
$env:OLLAMA_BASE_URL = "http://127.0.0.1:11434"
$env:HOTEL_EMBEDDING_MODEL = "embeddinggemma"
py .\load_hotel_policies.py `
  --input .\hotel_policy_chunks.jsonl `
  --embed ollama `
  --replace
```

### OpenAI 모델로 재임베딩

키는 명령행이나 파일에 쓰지 말고 현재 PowerShell 프로세스의 환경 변수로만 전달한다. `HOTEL_EMBEDDING_MODEL`을 생략하면 `text-embedding-3-small`을 사용한다.

```powershell
py -m pip install openai
$env:OPENAI_API_KEY = Read-Host "OPENAI API key"
$env:HOTEL_EMBEDDING_MODEL = "text-embedding-3-small"
py .\load_hotel_policies.py `
  --input .\hotel_policy_chunks.jsonl `
  --embed openai `
  --replace
```

`--replace`는 지정한 `--collection`만 지우며 다른 교재 컬렉션은 건드리지 않는다. 기본 컬렉션은 `hotel_policy`다.

## 파일 형식과 DB 스키마

`hotel_policy_chunks.jsonl`은 한 줄에 한 청크인 UTF-8 JSONL 텍스트본이다. 벡터 포함본은 같은 필드에 `embedding` 배열을 추가한다.

| JSONL 필드 | 의미 |
|---|---|
| `accommodation_id` | 여기어때 숙소 ID |
| `hotel_name` | 호텔명 |
| `city` | 시딩에 사용한 도시 |
| `section_title` | 기본정보, 인원 추가 정보, 편의시설 등의 규정 구분 |
| `chunk_index` | 호텔 안에서의 청크 순번 |
| `content` | 검색·답변 근거가 되는 규정 텍스트 |
| `sha` | `content`의 SHA-256 무결성 값 |
| `embedding` | 벡터 포함본에만 있는 실수 배열 |

로더가 사용하는 `documents` 스키마는 다음 열로 구성된다.

| 열 | 용도 |
|---|---|
| `id UUID` | UUID5 기반 청크 식별자 |
| `collection_name TEXT` | 기본값 `hotel_policy` |
| `title`, `content`, `source` | 제목, 규정 본문, `yeogi:<accommodation_id>` 출처 키 |
| `chunk_index INTEGER` | 호텔 내 청크 순번 |
| `embedding_provider`, `embedding_model`, `embedding_dimension` | 벡터 생성 정보 |
| `embedding VECTOR` | pgvector 검색 벡터 |
| `metadata JSONB` | 호텔 필터와 표시용 메타데이터 |
| `created_at TIMESTAMPTZ` | 적재 시각 |

`metadata`에는 `accommodation_id`(정수), `hotel_name`, `city`, `section_title`, `sha`가 들어간다.

특정 호텔의 규정을 검색할 때는 전체 호텔에서 유사도를 먼저 계산하면 안 된다. 반드시 `collection_name`과 `metadata->>'accommodation_id'`로 호텔을 먼저 제한한 뒤 그 결과 안에서 벡터 거리를 정렬한다.

```sql
SELECT title, content, metadata,
       1 - (embedding <=> CAST(:query_vector AS vector)) AS score
FROM documents
WHERE collection_name = 'hotel_policy'
  AND metadata->>'accommodation_id' = '123456'
ORDER BY embedding <=> CAST(:query_vector AS vector)
LIMIT 4;
```

## 출처와 주의사항

- 데이터 출처: 여기어때 웹 호텔 상세의 규정·편의시설 텍스트
- 수집일: 2026-08-28
- 용도: 수업 및 개인 학습을 위한 교육용 데이터
- 호텔 규정, 가격, 영업 상태는 수집 뒤 변경될 수 있다. 예약·결제 판단 전 여기어때와 호텔의 최신 공식 안내를 다시 확인해야 한다.
- 원문 서비스의 이용약관과 데이터 권리를 존중하고, 번들을 재배포하거나 상업적으로 사용하지 않는다.
