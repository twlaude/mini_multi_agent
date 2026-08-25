"""주차 화면과 카메라에서 사용하는 백엔드 API 함수 모음."""

from typing import Any, Literal

from core.api_client import BackendAPIError, request


Mode = Literal["workflow", "agent"]
Direction = Literal["enter", "exit"]
SpotEvent = Literal["occupied", "vacated"]
SobrietyResult = Literal["pass", "fail"]


def _unwrap(response: Any) -> Any:
    """주차 API 봉투를 해제합니다. 계약 확정 전의 일반 JSON도 임시 허용합니다."""
    if not isinstance(response, dict):
        return response
    if "success" not in response:
        return response
    if not response.get("success"):
        raise BackendAPIError(str(response.get("message") or "요청 처리에 실패했습니다."))
    return response.get("data")


def _validate(value: str, allowed: set[str], label: str) -> str:
    normalized = value.strip().lower()
    if normalized not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ValueError(f"{label} 값은 {choices} 중 하나여야 합니다.")
    return normalized


def get_parking_status() -> dict[str, Any]:
    data = _unwrap(request("GET", "/parking/status"))
    return data if isinstance(data, dict) else {}


def get_visitors(mode: Mode) -> Any:
    selected = _validate(mode, {"workflow", "agent"}, "mode")
    return _unwrap(request("GET", f"/parking/{selected}/visitors"))


def get_tailgating(mode: Mode) -> Any:
    selected = _validate(mode, {"workflow", "agent"}, "mode")
    return _unwrap(request("GET", f"/parking/{selected}/tailgating"))


def submit_gate(plate: str, direction: Direction, mode: Mode) -> dict[str, Any]:
    selected_mode = _validate(mode, {"workflow", "agent"}, "mode")
    selected_direction = _validate(direction, {"enter", "exit"}, "direction")
    data = _unwrap(
        request(
            "POST",
            f"/parking/{selected_mode}/gate",
            json={"plate": plate.strip(), "direction": selected_direction},
        )
    )
    return data if isinstance(data, dict) else {}


def submit_spot_event(spot_id: str, plate: str, event: SpotEvent) -> Any:
    selected = _validate(event, {"occupied", "vacated"}, "event")
    return _unwrap(
        request(
            "POST",
            "/parking/spot-event",
            json={"spot_id": spot_id.strip(), "plate": plate.strip(), "event": selected},
        )
    )


def submit_sobriety(check_id: int, result: SobrietyResult) -> Any:
    selected = _validate(result, {"pass", "fail"}, "result")
    return _unwrap(
        request("POST", f"/parking/sobriety/{check_id}", json={"result": selected})
    )


def ask_agent(question: str) -> Any:
    return _unwrap(
        request("POST", "/parking/agent/ask", json={"question": question.strip()})
    )


def as_items(data: Any, *field_names: str) -> list[dict[str, Any]]:
    """목록 또는 {items: [...]} 형태를 화면용 목록으로 정규화합니다."""
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    for name in (*field_names, "items", "results"):
        value = data.get(name)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def answer_text(data: Any) -> str:
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        for name in ("answer", "content", "message", "text"):
            value = data.get(name)
            if isinstance(value, str) and value:
                return value
    return "응답 내용을 표시할 수 없습니다. 백엔드 응답 계약을 확인해 주세요."
