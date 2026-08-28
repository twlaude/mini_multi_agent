"""공용 샘플 데이터와 가짜 client. 네트워크를 전혀 쓰지 않는다."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.clients import AccommodationClient, SearchPage  # noqa: E402
from app.clients.yeogi.parser import parse_hotel, parse_room_options  # noqa: E402

# 여기어때 응답 축약본
SAMPLE_ACCOMMODATION = {
    "meta": {
        "id": 12345,
        "name": "테스트 호텔",
        "grade": "호텔",
        "review": {"rate": 4.7, "count": 321},
        "address": {"traffic": "강남역 도보 5분"},
        "location": {"latitude": 37.49, "longitude": 127.02},
        "newImages": ["https://img.example/1.jpg"],
    },
    "room": {
        "stay": {"name": "스탠다드", "status": "AVAILABLE",
                 "price": {"discountTotalPrice": 89000, "strikePrice": 120000}},
        "rent": {"price": {"discountPrice": 40000}},
    },
}

SAMPLE_DETAIL = {
    "accommodationInfo": {
        "rooms": [
            {
                "id": 777,
                "name": "디럭스",
                "rent": {"price": {"discountTotalPrice": 35000}, "stockCount": 2,
                         "soldOut": False, "label": {"checkInOut": "4시간 이용"}},
                "stay": {"price": {"discountTotalPrice": 99000}, "stockCount": 0,
                         "soldOut": True, "label": {"checkInOut": "입실 22:00·퇴실 12:00"}},
            }
        ]
    }
}


class FakeClient(AccommodationClient):
    """search_page / room_options 호출을 기록하고 샘플을 돌려주는 가짜 client (다른 사이트 구현체의 예시이기도 함)."""

    def __init__(self, hotels_per_page=1, total_pages=1):
        self.calls = []
        self.hotels_per_page = hotels_per_page
        self.total_pages = total_pages

    def search_page(self, keyword, check_in, check_out, personal=2, page=1,
                    sort_type="RECOMMEND", category=None):
        self.calls.append({"page": page, "category": category, "sort": sort_type})
        hotels = [parse_hotel(SAMPLE_ACCOMMODATION, "https://www.yeogi.com")
                  for _ in range(self.hotels_per_page)]
        return SearchPage(items=hotels, total_pages=self.total_pages)

    def room_options(self, accommodation_id, check_in, check_out, personal=2):
        return parse_room_options(SAMPLE_DETAIL, accommodation_id)


@pytest.fixture
def fake_client():
    return FakeClient()
