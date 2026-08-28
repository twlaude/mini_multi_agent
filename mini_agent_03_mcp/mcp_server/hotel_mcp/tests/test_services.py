from datetime import date, timedelta

import pytest

from app.schemas import RENT, STAY
from app.services import checkout_service, room_service, search_service
from app.services.dates import check_date, default_dates
from tests.conftest import FakeClient

CHECKOUT = "https://platform.yeogi.com/domestic/checkout"


# ---------------------------------------------------------------- dates
def test_default_dates_fills_today_and_tomorrow():
    ci, co = default_dates("", "")
    assert ci == date.today().isoformat()
    assert co == (date.today() + timedelta(days=1)).isoformat()


def test_default_dates_rejects_bad_order_and_format():
    with pytest.raises(ValueError):
        default_dates("2026-09-06", "2026-09-05")
    with pytest.raises(ValueError):
        check_date("check_in", "2026/09/05")


# ---------------------------------------------------------------- search
def test_search_passes_category_code_and_truncates():
    client = FakeClient(hotels_per_page=20, total_pages=3)
    result = search_service.search_accommodations(client, "강남", category="호텔", max_results=25)
    assert client.calls[0]["category"] == "호텔"
    assert len(client.calls) == 2           # 25건 채우려면 2페이지(40건)면 충분
    assert result["count"] == 25
    assert result["sort"] == "평점높은순"
    assert set(result["items"][0]) == {
        "id", "name", "grade", "rating", "review_count", "traffic",
        "stay_price", "rent_price", "sold_out", "url",
    }


def test_search_rejects_bad_input(fake_client):
    with pytest.raises(ValueError):
        search_service.search_accommodations(fake_client, "   ")
    with pytest.raises(ValueError):
        search_service.search_accommodations(fake_client, "강남", max_results=0)


# ---------------------------------------------------------------- rooms
def test_room_options_output_shape(fake_client):
    result = room_service.get_room_options(fake_client, 12345, "2026-09-05", "2026-09-06")
    assert result["check_in"] == "2026-09-05"
    assert [o["kind"] for o in result["options"]] == ["rent", "stay"]
    assert result["options"][0]["available"] is True

# ---------------------------------------------------------------- checkout
def test_checkout_link_rent_vs_stay():
    rent = checkout_service.make_checkout_link(CHECKOUT, 12345, 777, RENT, "2026-09-05", "2026-09-06", "17:00")
    assert rent["checkout_url"].startswith(CHECKOUT + "?")
    assert "ano=12345" in rent["checkout_url"] and "armgno=777" in rent["checkout_url"]
    assert "checkinType=1" in rent["checkout_url"]
    assert rent["product"] == "대실" and rent["link_reproducible"] is False
    assert "17:00" in rent["manual_steps"][0]

    stay = checkout_service.make_checkout_link(CHECKOUT, 12345, 777, STAY, "2026-09-05", "2026-09-06")
    assert stay["product"] == "숙박" and stay["link_reproducible"] is True
    assert len(stay["manual_steps"]) == 1

    with pytest.raises(ValueError):
        checkout_service.make_checkout_link(CHECKOUT, 12345, 777, RENT, "2026-09-05", "2026-09-06", "1700")
