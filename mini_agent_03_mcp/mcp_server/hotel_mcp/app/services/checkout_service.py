"""Tool 3 — 결제 직전 페이지 링크 생성 (결제는 하지 않음)."""

from urllib.parse import urlencode

from app.schemas import RENT, SORT_TYPES, STAY
from app.services.dates import check_date


def build_checkout_url(checkout_base: str, accommodation_id: int, room_id: int,
                       checkin_type: int, check_in: str, check_out: str,
                       is_black: str = "N", biz_trip: str = "N") -> str:
    """결제 직전 페이지(예약 확인 및 결제) URL. 로그인된 브라우저로 열어야 함."""
    q = {
        "adcno": 1,
        "ano": accommodation_id,
        "armgno": room_id,
        "isBlack": is_black,
        "checkinType": checkin_type,
        "checkinDate": check_in,
        "checkoutDate": check_out,
        "bizTrip": biz_trip,
    }
    return f"{checkout_base}?{urlencode(q)}"


def make_checkout_link(checkout_base: str, accommodation_id: int, room_id: int,
                       checkin_type: int, check_in: str, check_out: str,
                       rent_start_time: str | None = None) -> dict:
    check_date("check_in", check_in)
    check_date("check_out", check_out)
    if checkin_type == RENT and rent_start_time and ":" not in rent_start_time:
        raise ValueError("rent_start_time은 'HH:MM' 형식이어야 합니다.")

    url = build_checkout_url(checkout_base, accommodation_id, room_id,
                             checkin_type, check_in, check_out)

    manual_steps = []
    if checkin_type == RENT:
        manual_steps.append(
            f"페이지에서 입실시각 '{rent_start_time or '원하는 시각'}' 버튼 클릭 (기본값은 첫 슬롯)")
        manual_steps.append("방문 방법(도보/차량) 선택")
    manual_steps.append("여기어때 로그인 후 약관 전체동의 체크, 결제 버튼은 사용자가 직접 클릭")

    return {
        "checkout_url": url,
        "product": "대실" if checkin_type == RENT else "숙박",
        "link_reproducible": checkin_type == STAY,
        "login_required": True,
        "manual_steps": manual_steps,
    }


def sort_types_text() -> str:
    """sort_type 값과 한글 의미 (yeogi://sort-types Resource)."""
    return "\n".join(f"{k}: {v}" for k, v in SORT_TYPES.items())
