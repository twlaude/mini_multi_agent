"""Tool 2 — 객실 옵션 조회 로직."""

from app.clients import AccommodationClient
from app.services.dates import default_dates


def get_room_options(client: AccommodationClient, accommodation_id: int, check_in: str = "",
                     check_out: str = "", personal: int = 2) -> dict:
    check_in, check_out = default_dates(check_in, check_out)
    opts = client.room_options(accommodation_id, check_in, check_out, personal)
    if not opts:
        raise ValueError(f"accommodation_id={accommodation_id} 객실 정보를 찾지 못했습니다.")
    return {
        "accommodation_id": accommodation_id,
        "check_in": check_in,
        "check_out": check_out,
        "options": [
            {
                "room_id": o.room_id,
                "room_name": o.room_name,
                "kind": o.kind,                    # "rent" | "stay"
                "checkin_type": o.checkin_type,    # 1=대실, 2=숙박
                "price": o.price,
                "stock": o.stock,
                "sold_out": o.sold_out,
                "available": o.available,
                "label": o.label,
                "max_hours": o.max_hours,
            }
            for o in opts
        ],
    }

