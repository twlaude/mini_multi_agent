# plan.md — 카메라 음성 가이드 (1-7)

## 목표

브라우저에서 맥북 카메라로 사진을 찍으면, 서버가 사진을 분석(묘사)하고
그 결과를 합성 음성으로 읽어주는 페이지를 만든다.

```
카메라 촬영 → 이미지 업로드 → LLM 묘사 → TTS 변환 → 자동 재생
```

## 배경

- `mini_agent_01_llm`의 기존 기능 재사용:
  - 1-5 이미지 분석 (`/api/media/image-analysis`) — 업로드 + vision 호출 패턴
  - 1-6 음성 생성 (`/api/media/tts`) — TTS 호출 패턴
- 기존 이미지 분석은 여행 테마(`TravelImageAnalysis` 스키마)로 고정되어 있어
  일반 사진 묘사에는 맞지 않음 → 순수 묘사용 엔드포인트를 새로 만든다.

## 설계

### Backend

| 항목 | 내용 |
| --- | --- |
| 엔드포인트 | `POST /api/media/image-describe` (multipart: `image`, `question`) |
| 스키마 | `ImageDescription { description: str }` — 여행 필드 없이 묘사 하나만 |
| 서비스 | `describe_image()` — 기존 `analyze_image()`와 같은 구조, 프롬프트만 "이미지를 한국어로 자연스럽게 묘사" |
| 검증 | 기존 `validate_image()` 재사용 (형식·시그니처·용량) |

### Frontend

| 항목 | 내용 |
| --- | --- |
| 페이지 | `app_pages/09_camera_voice_guide.py` (사이드바 1-7) |
| 카메라 | `st.camera_input` — 브라우저가 맥북 카메라 권한을 받아 스냅샷 촬영 |
| 클라이언트 | `core/api_client.py`에 `upload_image_describe()` 추가 |
| 재생 | 묘사 텍스트를 `/api/media/tts`로 보내 `st.audio(autoplay=True)` 재생 |

## 구현 단계

1. [x] Backend: `ImageDescription` 스키마 추가 (`schemas.py`)
2. [x] Backend: `describe_image()` 서비스 추가 (`services/media_service.py`)
3. [x] Backend: `/api/media/image-describe` 라우터 추가 (`routers/media_router.py`)
4. [x] Frontend: `upload_image_describe()` 클라이언트 추가 (`core/api_client.py`)
5. [x] Frontend: `09_camera_voice_guide.py` 페이지 작성 + `app.py` 메뉴 등록
6. [x] 검증: OpenAPI에 라우트 등록 확인, 문법 검사 통과
7. [ ] 실기 테스트: 카메라 촬영 → 묘사 → 음성 재생까지 브라우저에서 확인

## 두 번째 기능 — 음성 받아쓰기 (STT + 영어 번역)

같은 페이지 하단에 브라우저 마이크로 녹음한 음성을 텍스트로 변환하고,
영어로 번역해 함께 표시한다.

```
마이크 녹음 (st.audio_input) → 서버 업로드 → STT 변환 → 영어 번역 → 화면 표시
```

| 항목 | 내용 |
| --- | --- |
| 엔드포인트 | `POST /api/media/stt` (multipart: `audio`) → `{ text, english }` |
| STT | `transcribe_audio()` — OpenAI `gpt-4o-mini-transcribe`, 한국어 지정 |
| 번역 | `translate_to_english()` — STT 결과를 GPT로 영어 번역 (번역문만 출력) |
| 검증 | WAV/MP3/WEBM/MP4 형식·용량 제한 |
| 프론트 | `st.audio_input` 녹음 → `upload_audio_stt()` → 받아쓰기 결과 + 영어 번역 표시 |

1. [x] Backend: `transcribe_audio()` 서비스 + `/api/media/stt` 라우터
2. [x] Frontend: `upload_audio_stt()` 클라이언트 + 페이지 하단 STT 섹션
3. [x] Backend: `translate_to_english()` 추가, 응답에 `english` 포함
4. [x] Frontend: 받아쓰기 원문 + 영어 번역 함께 표시
5. [x] 검증: OpenAPI 라우트 등록 확인, 번역 함수 실호출 테스트 통과
6. [ ] 실기 테스트: 마이크 녹음 → 원문·영어 번역 표시 확인

## 파일 저장 정책

- 이미지·음성 파일은 디스크에 저장하지 않는다 — 업로드 바이트를 메모리에서
  처리해 OpenAI로 전달하고, 요청이 끝나면 자연 소멸된다. 별도 삭제 코드 불필요.

## 완료 기준

- 페이지에서 사진을 찍고 버튼을 누르면 묘사 텍스트가 화면에 표시된다.
- 묘사 결과가 합성 음성으로 자동 재생된다.
- 기존 1-5(여행 이미지 분석), 1-6(음성 생성) 페이지는 영향받지 않는다.

## 주의사항

- 카메라는 `localhost` 접속에서만 동작 (다른 기기에서 IP 접속 시 https가 아니면 브라우저가 차단)
- 여권·카드 등 민감한 이미지 촬영 금지 안내 유지
- 이미지 속 텍스트는 명령이 아닌 분석 대상으로 취급 (prompt injection 방지 문구 유지)
- TTS 입력은 2,000자 제한에 맞춰 잘라서 전송

## 확장 아이디어 (이번 범위 밖)

- 실시간 영상에서 사람 자동 감지: `streamlit-webrtc`로 프레임 스트림을 받아
  로컬 CV 모델(YOLO 등, `device="mps"`로 맥 GPU 활용)로 감지하고,
  감지 이벤트 때만 캡처해 묘사+TTS 파이프라인에 태우는 구조.
  프레임은 메모리에서 처리 후 버리므로 저장 용량 부담 없음.
