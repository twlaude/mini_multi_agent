"""숙소 데이터 소스가 지켜야 할 인터페이스.

services 는 이 인터페이스만 알고, 여기어때/야놀자 같은 실제 사이트 사정(URL·파라미터·응답 JSON)은
각 구현 패키지(clients/yeogi 등) 안에 가둔다. 새 사이트 = 이 클래스를 상속한 client 하나 + parser.
"""

from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.schemas import Hotel, RoomOption


class SearchPage(BaseModel):
    """검색 결과 한 페이지."""

    items: list[Hotel]
    total_pages: int = 1


class AccommodationClient(ABC):
    @abstractmethod
    def search_page(self, keyword: str, check_in: str, check_out: str, personal: int = 2,
                    page: int = 1, sort_type: str = "RECOMMEND",
                    category: str | None = None) -> SearchPage:
        """키워드·날짜로 숙소 한 페이지 검색. category 는 "호텔"/"모텔"/… 한글 이름(사이트별 코드 변환은 구현체 몫)."""

    @abstractmethod
    def room_options(self, accommodation_id: int, check_in: str, check_out: str,
                     personal: int = 2) -> list[RoomOption]:
        """숙소 한 곳의 해당 날짜 객실 × (대실/숙박) 옵션."""
