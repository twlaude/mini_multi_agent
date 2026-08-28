"""여기어때 응답을 단순한 숙소/객실 데이터로 다루기 위한 Schema."""

from pydantic import BaseModel


class RoomOption(BaseModel):
    """한 객실의 대실 또는 숙박 옵션 하나."""

    accommodation_id: int
    room_id: int              # = armgno
    room_name: str
    kind: str                 # "rent" | "stay"
    checkin_type: int         # RENT(1) | STAY(2)
    price: int | None
    stock: int
    sold_out: bool
    label: str | None         # "4시간 이용" / "입실 22:00·퇴실 12:00"
    max_hours: int | None     # 대실 최대 이용시간(시간)

    @property
    def available(self) -> bool:
        # 품절 아님 + 재고 있음 + 가격 있음 → 예약 가능
        return (not self.sold_out) and self.stock > 0 and bool(self.price)


class Hotel(BaseModel):
    """검색 결과 한 건(숙소 하나). clients.yeogi.parser.parse_hotel() 이 원본 JSON 에서 필요한 필드만 뽑아 만든다."""

    id: int | None
    name: str | None
    grade: str | None         # 모텔 / 호텔 / 펜션 ...
    rating: float | None
    review_count: int | None
    traffic: str | None       # "역삼역 도보 5분"
    lat: float | None
    lng: float | None
    stay_price: int | None    # 숙박 최저가(할인 적용)
    stay_strike: int | None   # 정가
    rent_price: int | None    # 대실가
    room_name: str | None
    sold_out: bool
    image: str | None
    url: str
