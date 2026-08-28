"""Tool 1 — 숙소 검색 로직."""

from app.clients import AccommodationClient
from app.schemas import SORT_TYPES
from app.services.dates import default_dates


def search_accommodations(client: AccommodationClient, keyword: str, check_in: str = "",
                          check_out: str = "", category: str = "전체", personal: int = 2,
                          sort_type: str = "HIRATING", max_results: int = 40) -> dict:
    if not keyword.strip():
        raise ValueError("keyword는 빈 문자열일 수 없습니다.")
    check_in, check_out = default_dates(check_in, check_out)
    if not 1 <= max_results <= 60:
        raise ValueError("max_results는 1~60 사이여야 합니다.")

    # 가격 필터는 일부러 없다 — 가격 조건 판단은 결과를 받은 AI 가 한다. 대신 AI 가 고를
    # 재료가 충분하도록 max_results 를 채울 때까지 페이지를 넘긴다 (최대 3페이지 = 60건).
    rows = []
    for page in range(1, 4):
        result = client.search_page(keyword.strip(), check_in, check_out, personal,
                                    page, sort_type, category=category)
        rows.extend(result.items)
        if not result.items or len(rows) >= max_results or page >= result.total_pages:
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
