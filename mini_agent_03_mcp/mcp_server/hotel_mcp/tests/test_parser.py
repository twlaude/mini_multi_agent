import pytest

from app.clients.yeogi.client import CATEGORY_CODES
from app.clients.yeogi.parser import extract_build_id, parse_hotel, parse_room_options, parse_search_page
from app.schemas import RENT, STAY
from tests.conftest import SAMPLE_ACCOMMODATION, SAMPLE_DETAIL


def test_parse_hotel_maps_nested_fields():
    h = parse_hotel(SAMPLE_ACCOMMODATION, "https://www.yeogi.com")
    assert (h.id, h.name, h.grade) == (12345, "테스트 호텔", "호텔")
    assert h.stay_price == 89000 and h.rent_price == 40000 and h.stay_strike == 120000
    assert h.sold_out is False
    assert h.url == "https://www.yeogi.com/domestic-accommodations/12345"


def test_parse_room_options_flattens_rent_and_stay():
    rent, stay = parse_room_options(SAMPLE_DETAIL, 12345)
    assert rent.kind == "rent" and rent.checkin_type == RENT and rent.max_hours == 4
    assert rent.available is True
    assert stay.kind == "stay" and stay.checkin_type == STAY and stay.max_hours is None
    assert stay.available is False  # 품절


def test_extract_build_id():
    assert extract_build_id('... "buildId":"abc123XYZ" ...') == "abc123XYZ"
    with pytest.raises(RuntimeError):
        extract_build_id("<html>no build id</html>")


def test_parse_search_page_and_category_codes():
    page = parse_search_page({"accommodationsData": [SAMPLE_ACCOMMODATION],
                              "paginationInfo": {"totalPageCount": 3}}, "https://www.yeogi.com")
    assert len(page.items) == 1 and page.total_pages == 3
    assert CATEGORY_CODES["호텔"] == 2 and "전체" not in CATEGORY_CODES
