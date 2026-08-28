"""여기어때 원본 JSON/HTML → Schema 변환. 네트워크를 전혀 쓰지 않으므로 단독 테스트가 가능합니다."""

import re
from typing import Any

from app.clients.base import SearchPage
from app.schemas import RENT, STAY, Hotel, RoomOption


def extract_build_id(html: str) -> str:
    """홈 HTML 안의 "buildId":"..." 문자열을 정규식으로 찾는다."""
    m = re.search(r'"buildId":"([^"]+)"', html)
    if not m:
        raise RuntimeError("buildId를 찾지 못함 (사이트 구조 변경 가능성)")
    return m.group(1)


def parse_hotel(a: dict[str, Any], base_url: str) -> Hotel:
    """여기어때 응답의 accommodationsData 항목 하나(a)를 Hotel 로 변환한다."""
    # 중첩된 dict 를 단계별로 꺼내되, 없는 키는 {} 로 받아 KeyError 를 피한다
    m = a.get("meta") or {}
    room = a.get("room") or {}
    stay = room.get("stay") or {}
    rent = room.get("rent") or {}
    sp = stay.get("price") or {}
    rp = rent.get("price") or {}
    rev = m.get("review") or {}
    loc = m.get("location") or {}
    addr = m.get("address") or {}
    imgs = m.get("newImages") or m.get("images") or []
    return Hotel(
        id=m.get("id"),
        name=m.get("name"),
        grade=m.get("grade"),
        rating=rev.get("rate"),
        review_count=rev.get("count"),
        traffic=addr.get("traffic"),
        lat=loc.get("latitude"),
        lng=loc.get("longitude"),
        stay_price=sp.get("discountTotalPrice") or sp.get("discountPrice"),
        stay_strike=sp.get("strikePrice"),
        rent_price=rp.get("discountTotalPrice") or rp.get("discountPrice"),
        room_name=stay.get("name") or rent.get("name"),
        sold_out=(stay.get("status") or rent.get("status")) == "SOLD_OUT",
        image=imgs[0] if imgs else None,
        url=f"{base_url}/domestic-accommodations/{m.get('id')}",
    )


def parse_search_page(page_props: dict[str, Any], base_url: str) -> SearchPage:
    """검색 pageProps → SearchPage. paginationInfo.totalPageCount 는 다음 페이지 판단용."""
    items = [parse_hotel(a, base_url) for a in (page_props.get("accommodationsData") or [])]
    total = (page_props.get("paginationInfo") or {}).get("totalPageCount") or 1
    return SearchPage(items=items, total_pages=total)


def parse_max_hours(label: str | None) -> int | None:
    """대실 라벨("4시간 이용")에서 최대 이용시간을 뽑는다."""
    if not label:
        return None
    m = re.search(r"(\d+)\s*시간", label)
    return int(m.group(1)) if m else None


def parse_room_options(page_props: dict[str, Any], accommodation_id: int) -> list[RoomOption]:
    """상세 pageProps 의 모든 객실 × (대실/숙박) 옵션을 평탄화해서 반환."""
    info = page_props.get("accommodationInfo") or {}
    out: list[RoomOption] = []
    # 객실마다 rent(대실)/stay(숙박) 두 종류를 각각 RoomOption 한 개로 펼친다
    for r in info.get("rooms") or []:
        for kind, ctype in (("rent", RENT), ("stay", STAY)):
            o = r.get(kind)
            if not o:
                continue
            price = o.get("price") or {}
            label = (o.get("label") or {}).get("checkInOut")
            out.append(RoomOption(
                accommodation_id=accommodation_id,
                room_id=r["id"],
                room_name=r.get("name") or "",
                kind=kind,
                checkin_type=ctype,
                price=price.get("discountTotalPrice") or price.get("discountPrice"),
                stock=o.get("stockCount") or 0,
                sold_out=bool(o.get("soldOut")),
                label=label,
                max_hours=parse_max_hours(label) if kind == "rent" else None,
            ))
    return out
