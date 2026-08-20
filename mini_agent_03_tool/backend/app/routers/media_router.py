from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile

from app.media import analyze_image, create_speech
from app.schemas import TtsRequest


media_router = APIRouter(prefix="/api/media", tags=["Multimodal"])


@media_router.post("/image-analysis")
async def image_analysis(image: UploadFile = File(...), question: str = Form("여행자가 알아야 할 정보와 주의점을 알려주세요.")) -> dict:
    try:
        return analyze_image(image.content_type or "", await image.read(), question).model_dump()
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"이미지 분석 실패: {error}") from error


@media_router.post("/tts")
def text_to_speech(payload: TtsRequest) -> Response:
    try:
        return Response(content=create_speech(payload.text, payload.voice, payload.instructions), media_type="audio/mpeg", headers={"X-Synthetic-Voice": "true"})
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"TTS 생성 실패: {error}") from error
