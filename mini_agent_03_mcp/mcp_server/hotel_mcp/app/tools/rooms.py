"""Tool 2 — get_room_options"""

from mcp.server.fastmcp import FastMCP

from app.core.deps import get_client
from app.services import room_service


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def get_room_options(
        accommodation_id: int,
        check_in: str = "",
        check_out: str = "",
        personal: int = 2,
    ) -> dict:
        """숙소 한 곳의 해당 날짜 객실별 대실(rent)/숙박(stay) 옵션과 재고를 조회합니다.

        available 이 true 인 옵션만 예약 가능합니다. 대실(rent)은 모텔에만 있으며
        max_hours 가 최대 이용시간입니다. room_id 와 checkin_type 을 make_checkout_link 에 넘기세요.
        """
        return room_service.get_room_options(get_client(), accommodation_id, check_in, check_out, personal)
