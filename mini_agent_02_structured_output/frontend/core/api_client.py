"""모든 페이지에서 공통으로 사용하는 HTTP 요청 기능 (응답 봉투 {"success","message","data"} 약속)."""

import os
from typing import Any

import httpx


# 성엽 컴 백엔드 주소. .env 또는 환경변수 BACKEND_URL 로 주입 (예: http://192.100.200.197:8000)
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
REQUEST_TIMEOUT = 70.0


class BackendAPIError(Exception):
    """Backend 연결 또는 API 응답 처리 중 발생한 오류입니다."""


def request(
    method: str,
    path: str,
    json: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    try:
        response = httpx.request(
            method,
            f"{BACKEND_URL}{path}",
            json=json,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
    except httpx.TimeoutException as error:
        raise BackendAPIError("백엔드 응답 시간이 초과되었습니다.") from error
    except httpx.RequestError as error:
        raise BackendAPIError("백엔드 서버에 연결할 수 없습니다. 서버 실행 상태를 확인해 주세요.") from error
    if response.is_error:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text or "알 수 없는 오류"
        raise BackendAPIError(f"요청에 실패했습니다 ({response.status_code}): {detail}")
    try:
        return response.json()
    except ValueError as error:
        raise BackendAPIError("백엔드가 올바른 JSON을 반환하지 않았습니다.") from error
