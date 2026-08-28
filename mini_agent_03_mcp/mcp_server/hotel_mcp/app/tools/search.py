"""Tool 1 — search_accommodations"""

from mcp.server.fastmcp import FastMCP

from app.core.deps import get_client
from app.schemas import Category, SortType
from app.services import search_service


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def search_accommodations(
        keyword: str,
        check_in: str = "",
        check_out: str = "",
        category: Category = "전체",
        personal: int = 2,
        sort_type: SortType = "HIRATING",
        max_results: int = 40,
    ) -> dict:
        """여기어때에서 국내 숙소를 실시간 검색합니다. 기본은 **평점 높은 순** 추천입니다.

        keyword 는 지역명·역명·숙소명 **짧은 한 단어** (예: "강남", "강남역", "해운대", "부산", "제주").
        "강남역 근처 호텔"처럼 수식어를 붙이면 0건이 나오므로 붙이지 말고, 숙소 유형은
        category 로 지정하세요 ("호텔"/"모텔"/"펜션"/"캠핑", 기본 "전체"). 사용자가 '호텔'이라고
        하면 category="호텔". check_in/check_out 은 YYYY-MM-DD, 생략하면 오늘~내일 1박.
        가격 조건("15만원 이하")은 이 Tool 이 거르지 않습니다 — 평점순 결과의 stay_price 를
        보고 조건에 맞는 숙소만 골라 답하세요 (기본 40건, 가격 조건이 빡세서 후보가 부족하면
        max_results=60 으로 다시 검색). sort_type 은 사용자가 "싼 순"처럼 정렬을 명시할 때만
        바꾸세요. 결과의 id 가 get_room_options 의 accommodation_id 입니다. stay_price 는 1박 최저가(원),
        rent_price 는 대실가(원, 모텔만 있음).
        """
        return search_service.search_accommodations(
            get_client(), keyword, check_in, check_out, category, personal, sort_type, max_results)
