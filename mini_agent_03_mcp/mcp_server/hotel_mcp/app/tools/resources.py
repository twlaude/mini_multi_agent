"""Resource 2개 — yeogi://sort-types, yeogi://today"""

from mcp.server.fastmcp import FastMCP

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
