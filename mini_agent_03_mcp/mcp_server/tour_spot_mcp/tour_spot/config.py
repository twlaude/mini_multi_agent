"""Tour Spot MCP가 사용하는 환경설정을 한곳에서 관리합니다."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class TourSpotSettings:
    service_key: str
    api_base_url: str
    mcp_host: str
    mcp_port: int
    api_timeout: float


def get_settings() -> TourSpotSettings:
    """환경변수를 읽어 타입이 정리된 설정을 반환합니다."""
    try:
        mcp_port = int(os.getenv("TOUR_SPOT_MCP_PORT", "8030"))
        api_timeout = float(os.getenv("TOUR_API_TIMEOUT", "10"))
    except ValueError as error:
        raise ValueError(
            "TOUR_SPOT_MCP_PORT와 TOUR_API_TIMEOUT은 숫자여야 합니다."
        ) from error

    if not 1 <= mcp_port <= 65_535:
        raise ValueError("TOUR_SPOT_MCP_PORT는 1~65535 범위여야 합니다.")
    if api_timeout <= 0:
        raise ValueError("TOUR_API_TIMEOUT은 0보다 커야 합니다.")

    return TourSpotSettings(
        service_key=os.getenv("TOUR_API_SERVICE_KEY", "").strip(),
        api_base_url=os.getenv(
            "TOUR_API_BASE_URL",
            "https://apis.data.go.kr/B551011/KorService2",
        ).rstrip("/"),
        mcp_host=os.getenv("TOUR_SPOT_MCP_HOST", "0.0.0.0").strip(),
        mcp_port=mcp_port,
        api_timeout=api_timeout,
    )
