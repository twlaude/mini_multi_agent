-- schema.sql — 주차 출입 시스템 테이블 정의 (plan_db.md 3절이 원본)
-- 실행: psql postgresql://parking:parking@localhost:5435/parking -f db/schema.sql
-- 전부 멱등(if not exists)이라 여러 번 실행해도 안전.

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
