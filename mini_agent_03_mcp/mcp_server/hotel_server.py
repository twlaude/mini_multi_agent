"""8030 포트에서 독립 실행되는 여기어때(yeogi.com) 숙소 검색 Streamable HTTP MCP Server입니다.

travel_server.py 와 같은 방식(FastMCP + streamable-http)이지만 mock 데이터 대신
**진짜 여기어때 검색 결과**를 돌려줍니다. 조회 로직은 옆의 ``yeogi_api.py``
(파이썬 표준 라이브러리만 사용, 로그인·쿠키·브라우저 전부 불필요)에 있고,
이 파일은 그 함수들을 MCP Tool/Resource 로 공개하는 역할만 합니다.

Tool 3개 (모두 인증 불필요)
    1. search_accommodations   지역 키워드+날짜(+최대 가격) → 숙소 목록
    2. get_room_options        숙소 id+날짜 → 객실별 대실/숙박 옵션·재고
    3. make_checkout_link      숙소 id+객실 id → 결제 직전 페이지 URL (결제는 하지 않음)

실행
    python mcp_server/hotel_server.py
    → http://<이 컴퓨터 IP>:8030/mcp   (다른 컴퓨터의 Backend 가 이 주소로 접속)

환경변수
    HOTEL_MCP_HOST  기본 0.0.0.0 (같은 네트워크의 다른 컴퓨터가 접속할 수 있게 모든 인터페이스에 바인딩)
    HOTEL_MCP_PORT  기본 8030

주의
    여기어때 공식 API 가 아니라 웹 페이지가 쓰는 Next.js data endpoint 를 그대로 읽습니다.
    스펙이 예고 없이 바뀔 수 있고, 과도한 호출은 차단될 수 있습니다 (교육용).
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode

from mcp.server.fastmcp import FastMCP

# 어느 디렉터리에서 실행하든 옆의 yeogi_api.py 를 import 할 수 있게 한다
sys.path.insert(0, str(Path(__file__).resolve().parent))
from yeogi_api import RENT, STAY, SORT_TYPES, Yeogi  # noqa: E402

MCP_HOST = os.getenv("HOTEL_MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("HOTEL_MCP_PORT", "8030"))

# Literal 로 두면 FastMCP 가 enum 으로 스키마에 넣어 GPT 가 허용값을 알게 된다
SortType = Literal[
    "RECOMMEND", "LOWPRICE", "HIPRICE", "HIRATING", "HIREVIEW",
    "HI_MEMBERSHIP_DISCOUNT", "DISTANCE",
]

# 숙소 유형 → 여기어때 검색 쿼리의 category 코드 (2026-08-27 실측: 1=모텔 2=호텔 3=펜션 5=캠핑, 없으면 전체)
Category = Literal["전체", "호텔", "모텔", "펜션", "캠핑"]
CATEGORY_CODES = {"호텔": 2, "모텔": 1, "펜션": 3, "캠핑": 5}

mcp = FastMCP(
    "hotel-search",
    instructions=(
        "여기어때(yeogi.com) 국내 숙소를 실시간으로 검색하고 객실 재고를 확인한 뒤 "
        "결제 직전 링크를 만드는 교육용 MCP Server. 검색 → 객실 옵션 → 결제 링크 순서로 "
        "호출한다. 로그인이 필요 없고, 결제는 절대 자동으로 하지 않는다."
    ),
    host=MCP_HOST,
    port=MCP_PORT,
    stateless_http=True,
    json_response=True,
)

_yeogi = Yeogi()  # buildId 캐시를 프로세스 안에서 공유


def _check_date(name: str, value: str) -> str:
    """YYYY-MM-DD 형식인지 검사하고 그대로 돌려준다."""
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{name}는 YYYY-MM-DD 형식이어야 합니다: {value!r}")
    return value


def _default_dates(check_in: str, check_out: str) -> tuple[str, str]:
    """날짜를 안 주면 오늘~내일(1박)로 채운다. check_in 만 주면 그 다음 날을 check_out 으로."""
    if not check_in:
        check_in = date.today().isoformat()
    _check_date("check_in", check_in)
    if not check_out:
        check_out = (date.fromisoformat(check_in) + timedelta(days=1)).isoformat()
    _check_date("check_out", check_out)
    if check_out <= check_in:
        raise ValueError("check_out은 check_in보다 뒤여야 합니다.")
    return check_in, check_out


# ---------------------------------------------------------------- Tool 1
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
    if not keyword.strip():
        raise ValueError("keyword는 빈 문자열일 수 없습니다.")
    check_in, check_out = _default_dates(check_in, check_out)
    if not 1 <= max_results <= 60:
        raise ValueError("max_results는 1~60 사이여야 합니다.")

    # category 코드는 검색 쿼리에 실어 여기어때 쪽에서 걸러 받는다 (한 페이지 20건).
    # 가격 필터는 일부러 없다 — 가격 조건 판단은 결과를 받은 AI 가 한다. 대신 AI 가 고를
    # 재료가 충분하도록 max_results 를 채울 때까지 페이지를 넘긴다 (최대 3페이지 = 60건).
    extra = {"category": CATEGORY_CODES[category]} if category in CATEGORY_CODES else None
    rows = []
    for page in range(1, 4):
        items, pag = _yeogi.search_page(keyword.strip(), check_in, check_out, personal,
                                        page, sort_type, extra=extra)
        rows.extend(items)
        if not items or len(rows) >= max_results or page >= (pag.get("totalPageCount") or 1):
            break
    items = [
        {
            "id": h.id,
            "name": h.name,
            "grade": h.grade,
            "rating": h.rating,
            "review_count": h.review_count,
            "traffic": h.traffic,
            "stay_price": h.stay_price,
            "rent_price": h.rent_price,
            "sold_out": h.sold_out,
            "url": h.url,
        }
        for h in rows[:max_results]
    ]
    return {
        "keyword": keyword,
        "check_in": check_in,
        "check_out": check_out,
        "category": category,
        "sort": SORT_TYPES[sort_type],
        "count": len(items),
        "items": items,
        "source": "yeogi.com (비공식 Next.js data endpoint)",
    }


# ---------------------------------------------------------------- Tool 2
@mcp.tool()
def get_room_options(
    accommodation_id: int,
    check_in: str = "",
    check_out: str = "",
    personal: int = 2,
) -> dict:
    """숙소 한 곳의 해당 날짜 객실별 대실(rent)/숙박(stay) 옵션과 재고를 조회합니다.

    available 이 true 인 옵션만 예약 가능합니다. 대실(rent)은 모텔에만 있으며
    max_hours 가 최대 이용시간입니다. room_id 와 checkin_type 을 make_checkout_link 에 넘기세요.
    """
    check_in, check_out = _default_dates(check_in, check_out)
    opts = _yeogi.room_options(accommodation_id, check_in, check_out, personal)
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


# ---------------------------------------------------------------- Tool 3
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
    _check_date("check_in", check_in)
    _check_date("check_out", check_out)
    if checkin_type == RENT and rent_start_time and ":" not in rent_start_time:
        raise ValueError("rent_start_time은 'HH:MM' 형식이어야 합니다.")

    query = {
        "adcno": 1,
        "ano": accommodation_id,
        "armgno": room_id,
        "isBlack": "N",
        "checkinType": checkin_type,
        "checkinDate": check_in,
        "checkoutDate": check_out,
        "bizTrip": "N",
    }
    url = f"https://platform.yeogi.com/domestic/checkout?{urlencode(query)}"

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


# ---------------------------------------------------------------- Resources
@mcp.resource("yeogi://sort-types")
def sort_types() -> str:
    """search_accommodations 의 sort_type 값과 한글 의미."""
    return "\n".join(f"{k}: {v}" for k, v in SORT_TYPES.items())


@mcp.resource("yeogi://today")
def today() -> str:
    """서버 기준 오늘/내일 날짜 (날짜 없는 질문의 기본값)."""
    return (
        f"today: {date.today().isoformat()}\n"
        f"tomorrow: {(date.today() + timedelta(days=1)).isoformat()}"
    )


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
