from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse

from app.domains.parking_common import ocr
from app.domains.parking_common.schemas import (
    SobrietyResultRequest,
    SpotEventRequest,
)
from app.domains.parking_common.service import (
    ParkingServiceError,
    get_health,
    get_parking_status,
    record_spot_event,
    resolve_sobriety_check,
)


parking_common_router = APIRouter(prefix="/parking", tags=["Parking"])


def _ok(message: str, data: dict) -> dict:
    return {"success": True, "message": message, "data": data}


def _error(message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "message": message, "data": None},
    )


@parking_common_router.post("/spot-event")
def spot_event(payload: SpotEventRequest):
    try:
        data = record_spot_event(payload.spot_id, payload.plate, payload.event)
        return _ok("주차면 이벤트를 기록했습니다.", data)
    except ParkingServiceError as error:
        return _error(str(error), error.status_code)
    except Exception as error:
        return _error(f"주차면 이벤트 기록 실패: {error}", 503)


@parking_common_router.post("/sobriety/{check_id}")
def sobriety_result(check_id: int, payload: SobrietyResultRequest):
    try:
        data = resolve_sobriety_check(check_id, payload.result)
        return _ok("음주측정 결과를 반영했습니다.", data)
    except ParkingServiceError as error:
        return _error(str(error), error.status_code)
    except Exception as error:
        return _error(f"음주측정 결과 반영 실패: {error}", 503)


@parking_common_router.get("/status")
def parking_status():
    try:
        return _ok("주차장 상태를 조회했습니다.", get_parking_status())
    except Exception as error:
        return _error(f"주차장 상태 조회 실패: {error}", 503)


MAX_IMAGE_BYTES = 5 * 1024 * 1024


@parking_common_router.post("/plate/recognize")
async def plate_recognize(image: UploadFile = File(...)):
    """카메라/스샷 이미지 → 번호판 문자열 (코드 단계 OCR). 프론트는 data.plate를 게이트 입력에 넣는다."""
    content = await image.read()
    if not content:
        return _error("이미지가 비어 있습니다.", 400)
    if len(content) > MAX_IMAGE_BYTES:
        return _error("이미지는 5MB 이하여야 합니다.", 413)
    try:
        data = ocr.recognize_plate(content)
    except ImportError:
        return _error("easyocr 미설치 — 백엔드에 `pip install easyocr` 필요", 503)
    except ocr.NotAnImageError as error:
        return _error(str(error), 400)
    except Exception as error:
        return _error(f"번호판 인식 실패: {error}", 500)
    if data["plate"] is None:
        return JSONResponse(
            status_code=422,
            content={"success": False, "message": "번호판을 못 읽었습니다.", "data": data},
        )
    return _ok("번호판을 인식했습니다.", data)


@parking_common_router.get("/health")
def parking_health() -> dict:
    return _ok("주차 서비스 상태를 조회했습니다.", get_health())
