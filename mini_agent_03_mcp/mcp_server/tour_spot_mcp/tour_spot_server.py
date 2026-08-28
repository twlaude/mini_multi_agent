"""8030 포트에서 실행되는 관광지 Streamable HTTP MCP Server입니다."""

import logging
import sys
from pathlib import Path


# 어느 디렉터리에서 실행해도 같은 폴더의 tour_spot 패키지를 찾게 합니다.
SERVER_ROOT = Path(__file__).resolve().parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from mcp.server.fastmcp import FastMCP

from tour_spot.config import get_settings
from tour_spot.repository import TourSpotRepository


settings = get_settings()
repository = TourSpotRepository(settings)

# httpx의 INFO 로그에는 query string이 포함될 수 있어 API 인증키 보호를 위해 숨깁니다.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

mcp = FastMCP(
    "tour-spot-port",
    instructions=(
        "한국관광공사 공공데이터를 사용해 대한민국 국내 관광지를 검색합니다. "
        "해외 관광지는 지원하지 않습니다."
    ),
    host=settings.mcp_host,
    port=settings.mcp_port,
    stateless_http=True,
    json_response=True,
)


@mcp.tool()
def search_tour_spots(location: str, limit: int = 5) -> dict:
    """대한민국 국내 지역의 관광지를 검색합니다.

    Args:
        location: 부산, 제주, 강릉, 경북 경주처럼 검색할 국내 지역명입니다.
        limit: 반환할 관광지 개수이며 1~10 범위입니다.
    """
    result = repository.search(location=location, limit=limit)
    return result.model_dump(mode="json")


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
