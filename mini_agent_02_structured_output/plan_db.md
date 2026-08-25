# plan_db.md — DB 구축 (담당: 태웅)

> **과제 본질 한 문장**: 주차 출입 시스템 — 번호판 인식 → 출입 판단 → 게이트 열림/닫힘 신호. **워크플로우 버전(고정 룰)** 과 **AI 에이전트 버전(Ollama tool-calling)** 두 벌을 같은 DB 위에서 만든다.
> **규모 상한**: 테이블 7개 이내, 시딩 스크립트 1개(~200줄). 그 이상이면 과설계.

## 0. 공통 아키텍처 (3명 공유 — 이 블록은 세 plan 모두 동일)

```
[카메라(웹캠) → 번호판 OCR]  ──plate 문자열──▶  [FastAPI 백엔드]  ──SQL──▶  [Docker PG]
        (오현님)                                   (성엽)                    (태웅)
                                                     │
                          워크플로우 버전: if/else 고정 룰
                          에이전트 버전:  Ollama(도커, 오현님 세팅)가 툴 골라 쓰며 판단
                                                     │
                                            [Streamlit 프론트] (오현님)
```

- **기능 3개** (두 버전 각각 구현):
  1. **외부인 차량 조회** — 지금 주차장에 있는 미등록/방문 차량 목록
  2. **이상 시간대 출차 → 음주 체크** — 평소 출차 시간대와 다른 새벽/심야 출차면 (가짜) 음주측정 요청, 통과해야 게이트 오픈
  3. **꼬리물기 탐지** — 각 주차면에 번호인식 장치가 있다고 가정. 자리에서 관측됐는데 게이트 입차 기록이 없는 번호 = 꼬리물기
- **작업 위치**: 이 repo의 `mini_agent_02_structured_output/` — 기존 `backend/`(FastAPI)와 `frontend/`(Streamlit) 뼈대 **위에서 개조**. 계층 구조(백엔드 `app/routers → services → schemas`, 프론트 `app_pages → clients → core/api_client`)는 유지하고, 여행루트 도메인 파일들은 참고하거나 지우고 주차 도메인으로 교체
- **응답 봉투**: `{"success": bool, "message": str, "data": ...}` (기존 api_client.py 약속 유지)
- **DB 접속 (백엔드가 쓸 DSN)**: `postgresql://parking:parking@<태웅IP>:5432/parking`
  (태웅 본인 컴에서만 `localhost:5432`. 컨테이너 이름 `pg` — 프로젝트별로 새로 만들지 않고 DB만 추가해서 공용)
- ⚠️ 뼈대는 supabase 클라이언트인데 이번엔 로컬 PG니까 백엔드는 **psycopg**로 접속 (plan_backend.md 참조)
- **배포 방식: git 없음 + 역할별 분산 호스팅** — 같은 네트워크(교실 와이파이 또는 핫스팟)에서 **각자 자기 담당만 자기 컴에 띄우고 서로 IP로 접속**:
  · 태웅 컴 = **DB** (docker PG :5432) ← 성엽 백엔드가 원격 접속
  · 성엽 컴 = **백엔드** (uvicorn `--host 0.0.0.0 --port 8000`) ← 오현님 프론트·카메라가 원격 접속
  · 오현님 컴 = **프론트**(streamlit) + **Ollama**(docker :11434) + 카메라 ← Ollama는 성엽 백엔드가 원격 호출
- **IP 교환이 첫 일**: 각자 자기 IP 확인(맥 `ipconfig getifaddr en0` / 윈도우 `ipconfig`)해서 디코에 공유. IP·포트는 코드에 하드코딩 말고 **.env**로 (와이파이 바뀌면 IP 바뀜). API 경로·포트·스키마 계약은 임의 변경 금지
- ⚠️ 교실 공용 와이파이가 기기 간 통신을 막으면(클라이언트 격리) 폰 핫스팟 하나에 셋 다 붙는 걸로 폴백. 각자 OS 방화벽에서 해당 포트 인바운드 허용 필요할 수 있음

## 1. 목표
Docker PG 컨테이너 + 스키마 + 가짜 데이터 시딩까지. 백엔드가 DSN만 받아서 바로 쿼리할 수 있는 상태가 산출물.

## 2. 컨테이너

```bash
docker run -d --name pg -p 5432:5432 \
  -e POSTGRES_USER=parking -e POSTGRES_PASSWORD=parking -e POSTGRES_DB=parking \
  postgres:16
```

## 3. 스키마 (schema.sql — 멱등으로 작성, 여러 번 실행 안전)

```sql
-- 등록 차량 (입주민/직원). 여기 없으면 외부인
create table if not exists vehicles (
  plate       text primary key,          -- '12가3456'
  owner_name  text not null,
  vehicle_type text not null default 'resident'  -- resident | staff
    check (vehicle_type in ('resident','staff')),
  registered_at timestamptz not null default now()
);

-- 게이트 이벤트 (입차/출차 시도 전부 기록 — 판단 결과 포함)
create table if not exists gate_events (
  id          bigint generated always as identity primary key,
  plate       text not null,
  direction   text not null check (direction in ('enter','exit')),
  decision    text not null check (decision in ('open','deny','hold')),  -- hold=음주측정 대기
  reason      text not null,             -- 판단 근거 (에이전트 버전은 LLM이 쓴 사유)
  mode        text not null check (mode in ('workflow','agent')),
  created_at  timestamptz not null default now()
);

-- 주차면
create table if not exists parking_spots (
  spot_id     text primary key,          -- 'A-01' ~ 'A-20'
  floor       text not null default 'B1'
);

-- 자리 센서 이벤트 (각 자리의 번호인식 장치가 쌓는 로그 — 꼬리물기 탐지 원천)
create table if not exists spot_events (
  id          bigint generated always as identity primary key,
  spot_id     text not null references parking_spots(spot_id),
  plate       text not null,
  event       text not null check (event in ('occupied','vacated')),
  created_at  timestamptz not null default now()
);

-- 음주측정 요청/결과 (가짜 측정)
create table if not exists sobriety_checks (
  id          bigint generated always as identity primary key,
  plate       text not null,
  status      text not null default 'pending'
    check (status in ('pending','pass','fail')),
  requested_at timestamptz not null default now(),
  resolved_at  timestamptz
);

-- 경보 (꼬리물기 등)
create table if not exists alerts (
  id          bigint generated always as identity primary key,
  alert_type  text not null check (alert_type in ('tailgating','drunk_suspect')),
  plate       text not null,
  detail      text not null,
  resolved    boolean not null default false,
  created_at  timestamptz not null default now()
);
```

- **"평소 출차 시간대" 테이블은 안 만든다** — 과거 30일 gate_events에서 `avg/stddev(extract(hour from created_at))`로 즉석 계산 (기능 2용). 테이블 추가는 과설계.
- **현재 주차중 차량**도 테이블 없이 도출: 마지막 gate_events가 enter인 plate (또는 마지막 spot_events가 occupied).

## 4. 가짜 데이터 시딩 (seed.py 1개)

시나리오가 기능 3개를 전부 커버해야 함:
1. **등록 차량 8대** — vehicles에 insert. 이 중 6대는 지난 30일간 규칙적 패턴의 입출차 이력 생성 (예: '12가3456'은 매일 08시경 출차·19시경 입차 → 기능 2의 "평소 시간대" 근거)
2. **외부인 3대** — vehicles에 없음. 그중 2대는 오늘 정상 입차 기록(enter/open), 현재 주차중 상태 + spot_events occupied → 기능 1 조회 대상
3. **꼬리물기 1대** — gate_events에 enter 기록 **없이** spot_events에만 occupied로 등장 (예: '99허9999'가 A-13에) → 기능 3이 잡아내는 정답
4. parking_spots 20면 생성, 주차중 차량들 자리 배정

검증 쿼리 3개를 seed.py 끝에 assert로 넣기 (외부인 2대 조회됨 / 12가3456 평균 출차시각 19시대 / 꼬리물기 후보 1건).

## 5. 단계
1. 컨테이너 기동 + schema.sql 적용
2. seed.py 작성·실행 (`psycopg` 사용, `pip install psycopg[binary]`)
3. 검증 쿼리 통과 확인
4. 성엽한테 DSN + 이 파일의 스키마 공유 → 백엔드 붙는 것 확인

## 6. 완료 기준
- [ ] `psql postgresql://parking:parking@localhost:5432/parking -c '\dt'` 테이블 6개
- [ ] seed 검증 assert 3개 통과
- [ ] 백엔드에서 SELECT 성공 (성엽 헬스체크 라우터로 확인)

## 7. 금지사항
- ORM/마이그레이션 도구(alembic 등) 도입 금지 — schema.sql 직실행이면 충분
- 시딩 데이터에 실제 차량번호/개인정보 사용 금지
