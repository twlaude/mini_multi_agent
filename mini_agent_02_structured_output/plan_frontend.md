# plan_frontend.md — 프론트 + 카메라 번호인식 + Ollama (담당: 오현님)

> **과제 본질 한 문장**: 주차 출입 시스템 — 번호판 인식 → 출입 판단 → 게이트 열림/닫힘 신호. **워크플로우 버전(고정 룰)** 과 **AI 에이전트 버전(Ollama tool-calling)** 두 벌을 같은 DB 위에서 만든다.
> **규모 상한**: Streamlit 탭 3개 + 카메라 스크립트 1개(~150줄) + Ollama 컨테이너 1개. 그 이상이면 과설계.

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

- **기능 3개** (두 버전 각각): ① 외부인 차량 조회 ② 이상 시간대 출차 → 음주 체크 ③ 꼬리물기 탐지
- **작업 위치**: 이 repo의 `mini_agent_02_structured_output/frontend/` — 기존 뼈대(`app.py` 내비게이션 + `app_pages → clients → core/api_client.py`) **위에서 개조**. 주차 페이지 3개를 app_pages에 추가하고 app.py 내비에 등록, 여행 페이지들은 참고 후 제거 가능. 백엔드 주소 env 변수명은 뼈대 코드 그대로 **`BACKEND_API_URL`**
- **응답 봉투**: `{"success", "message", "data"}`
- **백엔드 API 계약**: plan_backend.md 2절 표가 SSOT — 카메라는 인식한 **번호 문자열만** `POST /parking/{mode}/gate`로 쏘면 끝 (비전 결과를 DB에 직접 쓰지 않음)
- **배포 방식: git 없음 + 역할별 분산 호스팅** — 같은 네트워크에서 각자 담당만 자기 컴에 띄우고 서로 IP로 접속 (태웅=DB:5435 / 성엽=백엔드:8000 / 오현님=프론트+Ollama:11434+카메라). 프론트·카메라의 백엔드 주소는 `http://<성엽IP>:8000` (.env `BACKEND_API_URL`로 주입 — 뼈대 api_client.py가 읽는 이름. 하드코딩 금지)
- **Ollama는 성엽 백엔드가 원격 호출** — 도커 `-p 11434:11434`는 이미 전체 인터페이스 바인딩이라 그대로 두면 되고, OS 방화벽이 11434 인바운드를 막지 않는지만 확인. 계약(경로·포트) 임의 변경 금지
- ⚠️ 와이파이가 기기 간 통신 막으면(클라이언트 격리) 폰 핫스팟 하나에 셋 다 붙는 걸로 폴백

## 1. Ollama (도커)

- **모델 `llama3.2` 확정** (2026-08-24 현장 결정 — 이미 설치돼 있음, tool calling 지원). 새로 받을 것 없음
- Ollama가 외부(성엽 백엔드)에서 접속돼야 함: 설치판이면 `OLLAMA_HOST=0.0.0.0` 환경변수 + 재시작, 방화벽 11434 인바운드 허용
- 검증: `curl localhost:11434/v1/models` 200 + 성엽 컴에서 `curl http://<오현님IP>:11434/v1/models` 200. 시연 전에 워밍업 호출 한 번 (첫 호출은 모델 로드 때문에 느림)

## 2. 카메라 번호인식 (camera_reader.py — Streamlit 밖 단독 스크립트)

- **입력 소스**: 웹캠에 A4로 출력한 가짜 번호판(`12가3456` 크게 인쇄)을 들이대는 방식
- **1차(오늘 목표)**: YOLO 없이 간다 — `easyocr`(ko+en)로 프레임 전체에서 텍스트 뽑고 번호판 정규식 `\d{2,3}[가-힣]\d{4}` 매칭. A4 인쇄물이면 이걸로 충분히 잡힘
- **2차(시간 남으면)**: 사전학습 번호판 YOLO로 crop 후 OCR — 정확도 개선용 옵션. 처음부터 하지 말 것
- 동작: 같은 번호가 연속 3프레임 잡히면 확정 → `POST /parking/{mode}/gate` 호출 → 응답 decision을 터미널+화면에 표시 → 동일 번호 30초 쿨다운(중복 방지)
- mode(workflow/agent)와 direction(enter/exit)은 실행 인자로: `python camera_reader.py --mode agent --direction exit`
- 웹캠 안 되는 상황 대비: `--image plate.jpg` 옵션으로 정지 이미지도 받게 (데모 보험)

## 3. Streamlit 페이지 3개 (frontend/app_pages/에 추가)

### ① 관제 대시보드 (parking_dashboard_tab.py)
- `GET /parking/status` 폴링 — 주차면 20칸 그리드(점유=번호 표시), 최근 게이트 이벤트 테이블, 미해결 alerts 빨간 배지
- **외부인 조회 버튼**: 워크플로우/에이전트 라디오로 mode 골라서 `/parking/{mode}/visitors` → 결과 비교가 데모 포인트
- **꼬리물기 점검 버튼**: `/parking/{mode}/tailgating`

### ② 게이트 시뮬레이터 (parking_gate_tab.py) — 카메라 없이도 전 시나리오 시연용
- 번호 입력 + enter/exit + mode 선택 → `/parking/{mode}/gate` 호출, decision/reason 크게 표시
- **음주측정 패널**: pending 상태 sobriety_checks 목록 + [통과]/[불합격] 버튼 → `POST /parking/sobriety/{id}` (가짜 측정기 역할)
- **자리 센서 패널**: spot_id + 번호 + occupied/vacated → `POST /parking/spot-event` (꼬리물기 연출용 — 게이트 안 거치고 자리에 번호 등장시키기)

### ③ 관제 챗봇 (parking_chat_tab.py) — 에이전트 버전 전용
- 채팅 입력 → `POST /parking/agent/ask` — "지금 외부인 누구 있어?", "새벽에 나간 차 있어?" 자연어 질의
- 기존 chat 탭 코드 재활용

## 4. 단계
1. Ollama 컨테이너 + 모델 pull (성엽이 에이전트 개발 시작하기 전에 — **제일 먼저**)
2. 게이트 시뮬레이터 탭 (백엔드 버전 A 나오는 즉시 붙여서 시나리오 검증)
3. 대시보드 탭
4. camera_reader.py 1차 (easyocr)
5. 챗봇 탭 (백엔드 `/ask` 나온 뒤)

## 5. 완료 기준
- [ ] 시뮬레이터만으로 3기능 × 2버전 전부 시연 가능 (카메라는 보너스)
- [ ] A4 번호판 웹캠 인식 → 게이트 호출 → decision 표시 E2E 1회 성공
- [ ] 대시보드에서 꼬리물기 alert 빨간 배지 확인

## 6. 금지사항
- 카메라 인식 결과를 DB에 직접 쓰지 말 것 — 반드시 백엔드 API 경유 (계층 붕괴 방지)
- OCR confidence 튜닝에 30분 이상 쓰지 말 것 — 안 잡히면 인쇄물 크기/조명부터 바꾸고, 그래도 안 되면 시뮬레이터로 데모
