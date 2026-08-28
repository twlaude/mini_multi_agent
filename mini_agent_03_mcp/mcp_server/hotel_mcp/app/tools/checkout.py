"""Tool 3 — make_checkout_link"""

from typing import Literal

from mcp.server.fastmcp import FastMCP

from app.core.deps import get_app_settings
from app.services import checkout_service


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def make_checkout_link(
        accommodation_id: int,
        room_id: int,
        checkin_type: Literal[1, 2],
        check_in: str,
        check_out: str,
        rent_start_time: str | None = None,
    ) -> dict:
        """결제 직전 페이지(예약 확인 및 결제) URL을 만듭니다. 결제는 하지 않습니다.

        checkin_type: 1=대실, 2=숙박. 대실이면 rent_start_time("17:00")을 함께 주세요 —
        입실시각은 URL에 실리지 않아 사용자가 페이지에서 직접 눌러야 합니다.
        이 링크는 사용자가 여기어때에 로그인된 브라우저에서 직접 열어야 합니다.
        """
        return checkout_service.make_checkout_link(
            get_app_settings().checkout_url, accommodation_id, room_id,
            checkin_type, check_in, check_out, rent_start_time)
