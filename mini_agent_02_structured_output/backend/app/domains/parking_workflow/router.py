from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.domains.parking_workflow import service
from app.domains.parking_workflow.schemas import GateRequest


parking_workflow_router = APIRouter(
    prefix="/parking/workflow", tags=["parking-workflow"]
)


def _error(error: Exception) -> JSONResponse:
    status = 400 if isinstance(error, ValueError) else 500
    return JSONResponse(
        status_code=status,
        content={"success": False, "message": str(error), "data": None},
    )


@parking_workflow_router.post("/gate")
def gate(payload: GateRequest):
    try:
        data = service.process_gate(payload)
        return {"success": True, "message": "게이트 판단 완료", "data": data}
    except Exception as error:
        return _error(error)


@parking_workflow_router.get("/visitors")
def visitors():
    try:
        data = service.list_visitors()
        return {"success": True, "message": "외부인 차량 조회 완료", "data": data}
    except Exception as error:
        return _error(error)


@parking_workflow_router.get("/tailgating")
def tailgating():
    try:
        data = service.list_tailgating()
        return {"success": True, "message": "꼬리물기 의심 조회 완료", "data": data}
    except Exception as error:
        return _error(error)
