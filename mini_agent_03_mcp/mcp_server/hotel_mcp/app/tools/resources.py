"""여기어때 검색·규정 상태 Resource 등록."""

import json

from mcp.server.fastmcp import FastMCP

from app.core.deps import get_store
from app.services import checkout_service, dates


def register(mcp: FastMCP) -> None:
    @mcp.resource("yeogi://sort-types")
    def sort_types() -> str:
        """search_accommodations 의 sort_type 값과 한글 의미."""
        return checkout_service.sort_types_text()

    @mcp.resource("yeogi://today")
    def today() -> str:
        """서버 기준 오늘/내일 날짜 (날짜 없는 질문의 기본값)."""
        return dates.today_text()

    @mcp.resource("yeogi://policy-stats")
    def policy_stats() -> str:
        """현재 임베딩 설정으로 적재된 호텔 수와 규정 청크 수."""
        return json.dumps(get_store().stats(), ensure_ascii=False)
