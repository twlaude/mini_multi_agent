"""Hotel MCP가 사용하는 환경설정을 한곳에서 관리합니다."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]  # hotel_mcp/
load_dotenv(PROJECT_ROOT / ".env")

# 브라우저인 척하기 위한 User-Agent (없으면 차단될 수 있음)
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class HotelSettings:
    mcp_host: str
    mcp_port: int
    base_url: str        # 여기어때 웹 (검색·상세 데이터 endpoint 의 기준 주소)
    checkout_url: str    # 결제 직전 페이지
    user_agent: str
    request_timeout: int  # HTTP 요청 제한 시간(초)
    page_delay: float     # 페이지 넘길 때 쉬는 시간(초, 차단 방지)


def get_settings() -> HotelSettings:
    """환경변수를 읽어 타입이 정리된 설정을 반환합니다."""
    try:
        mcp_port = int(os.getenv("HOTEL_MCP_PORT", "8030"))
        request_timeout = int(os.getenv("YEOGI_TIMEOUT", "15"))
        page_delay = float(os.getenv("YEOGI_PAGE_DELAY", "0.4"))
    except ValueError as error:
        raise ValueError(
            "HOTEL_MCP_PORT, YEOGI_TIMEOUT, YEOGI_PAGE_DELAY는 숫자여야 합니다."
        ) from error

    if not 1 <= mcp_port <= 65_535:
        raise ValueError("HOTEL_MCP_PORT는 1~65535 범위여야 합니다.")

    return HotelSettings(
        mcp_host=os.getenv("HOTEL_MCP_HOST", "0.0.0.0").strip(),
        mcp_port=mcp_port,
        base_url=os.getenv("YEOGI_BASE_URL", "https://www.yeogi.com").rstrip("/"),
        checkout_url=os.getenv(
            "YEOGI_CHECKOUT_URL", "https://platform.yeogi.com/domestic/checkout"
        ),
        user_agent=os.getenv("YEOGI_USER_AGENT", DEFAULT_USER_AGENT),
        request_timeout=request_timeout,
        page_delay=page_delay,
    )
