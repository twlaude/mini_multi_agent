from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile

from app.schemas import TtsRequest
from app.services.media_service import (
    analyze_image,
    create_speech,
    describe_image,
    transcribe_audio,
    translate_to_english,
)


media_router = APIRouter(prefix="/api/media", tags=["Multimodal"])


@media_router.post("/image-analysis")
async def image_analysis(
    image: UploadFile = File(...),
    question: str = Form("여행자가 알아야 할 정보와 주의점을 알려주세요."),
) -> dict:
    try:
        result = analyze_image(image.content_type or "", await image.read(), question)
        return result.model_dump()
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"이미지 분석 실패: {error}") from error


@media_router.post("/image-describe")
async def image_describe(
    image: UploadFile = File(...),
    question: str = Form("이 사진에 무엇이 보이는지 자세히 묘사해주세요."),
) -> dict:
    try:
        result = describe_image(image.content_type or "", await image.read(), question)
        return result.model_dump()
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"이미지 묘사 실패: {error}") from error


@media_router.post("/stt")
async def speech_to_text(audio: UploadFile = File(...)) -> dict:
    try:
        text = transcribe_audio(
            audio.content_type or "", await audio.read(), audio.filename or "audio.wav"
        )
        english = translate_to_english(text) if text.strip() else ""
        return {"text": text, "english": english}
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"음성 인식 실패: {error}") from error


@media_router.post("/tts")
def text_to_speech(payload: TtsRequest) -> Response:
    try:
        audio = create_speech(payload.text, payload.voice, payload.instructions)
        return Response(
            content=audio,
            media_type="audio/mpeg",
            headers={"X-Synthetic-Voice": "true"},
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"TTS 생성 실패: {error}") from error
