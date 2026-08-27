#!/usr/bin/env python3
"""
여기어때(yeogi.com) 비공식 검색 클라이언트

원리:
  여기어때 웹은 Next.js(Pages Router) SSR. 검색 결과는 페이지 HTML의
  __NEXT_DATA__ 안에 통째로 들어있고, 같은 데이터를 아래 경로가 순수 JSON으로 뱉는다.

    GET https://www.yeogi.com/_next/data/{buildId}/domestic-accommodations.json?<검색쿼리>
    (헤더: x-nextjs-data: 1)

  buildId는 배포될 때마다 바뀌므로 https://www.yeogi.com/ HTML에서 매번 긁어온다.
  쿠키/로그인/토큰 전부 불필요. 브라우저도 불필요.

주의: 공식 API 아님. 언제든 스펙이 바뀔 수 있고 과도한 호출은 차단 대상.

파일 관계:
  mcp_server.py 의 Tool 1~3(search_accommodations / get_room_options / make_checkout_link)이
  이 파일의 Yeogi 클래스를 쓴다. 브라우저 없이 HTTP 만 쓰는 '조회 계층'이고,
  로그인/결제 직전 세팅(브라우저 필요)은 yeogi_login.py / yeogi_checkout.py 가 맡는다.
  단독 실행(python yeogi_api.py 강남 2026-09-05 2026-09-06)도 가능하다.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

# 브라우저인 척하기 위한 User-Agent (없으면 차단될 수 있음)
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")

BASE = "https://www.yeogi.com"
CHECKOUT = "https://platform.yeogi.com/domestic/checkout"

# 체크아웃 URL의 checkinType
RENT = 1   # 대실 (시간단위, 체크아웃페이지에서 입실시각 선택)
STAY = 2   # 숙박 (1박 이상, 입/퇴실 시각 고정)

# 정렬 옵션 코드 → 한글 의미. mcp_server 의 SortType Literal 과 yeogi://sort-types Resource 가 참조
SORT_TYPES = {
    "RECOMMEND": "추천순",
    "HI_MEMBERSHIP_DISCOUNT": "할인율 높은순",
    "HIRATING": "평점높은순",
    "HIREVIEW": "리뷰많은순",
    "LOWPRICE": "낮은가격순",
    "HIPRICE": "높은가격순",
    "DISTANCE": "거리순",
}


@dataclass
class RoomOption:
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

    def checkout_url(self, check_in: str, check_out: str,
                     is_black: str = "N", biz_trip: str = "N") -> str:
        """결제 직전 페이지(예약 확인 및 결제) URL. 로그인된 브라우저로 열어야 함."""
        q = {
            "adcno": 1,
            "ano": self.accommodation_id,
            "armgno": self.room_id,
            "isBlack": is_black,
            "checkinType": self.checkin_type,
            "checkinDate": check_in,
            "checkoutDate": check_out,
            "bizTrip": biz_trip,
        }
        return f"{CHECKOUT}?{urlencode(q)}"


@dataclass
class Hotel:
    """검색 결과 한 건(숙소 하나). from_raw() 가 원본 JSON 에서 필요한 필드만 뽑아 만든다."""
    id: int
    name: str
    grade: str            # 모텔 / 호텔 / 펜션 ...
    rating: float | None
    review_count: int | None
    traffic: str | None   # "역삼역 도보 5분"
    lat: float | None
    lng: float | None
    stay_price: int | None    # 숙박 최저가(할인 적용)
    stay_strike: int | None   # 정가
    rent_price: int | None    # 대실가
    room_name: str | None
    sold_out: bool
    image: str | None
    url: str

    @classmethod
    def from_raw(cls, a: dict[str, Any]) -> "Hotel":
        """여기어때 응답의 accommodationsData 항목 하나(a)를 Hotel 로 변환한다. search_page() 가 호출."""
        # 중첩된 dict 를 단계별로 꺼내되, 없는 키는 {} 로 받아 KeyError 를 피한다
        m = a.get("meta") or {}
        room = a.get("room") or {}
        stay = room.get("stay") or {}
        rent = room.get("rent") or {}
        sp = (stay.get("price") or {})
        rp = (rent.get("price") or {})
        rev = m.get("review") or {}
        loc = m.get("location") or {}
        addr = m.get("address") or {}
        imgs = m.get("newImages") or m.get("images") or []
        return cls(
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
            url=f"{BASE}/domestic-accommodations/{m.get('id')}",
        )


class Yeogi:
    """여기어때 조회 클라이언트. 의존성 없음 (파이썬 표준 라이브러리만 사용).

    buildId 를 한 번 얻어 캐시하고, search / detail / room_options 로 조회한다.
    mcp_server.py 가 프로세스당 인스턴스 하나(_yeogi)를 만들어 공유한다.
    """

    def __init__(self, delay: float = 0.4, timeout: int = 15):
        # delay = 페이지 넘길 때 쉬는 시간(초, 차단 방지), timeout = HTTP 요청 제한 시간(초)
        self._build_id: str | None = None
        self.delay = delay
        self.timeout = timeout

    def _get(self, url: str, headers: dict | None = None) -> str:
        """URL 을 GET 해서 본문 문자열을 돌려주는 최소 HTTP 도우미. 이 클래스의 모든 요청이 거쳐 간다."""
        h = {"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"}
        h.update(headers or {})
        with urlopen(Request(url, headers=h), timeout=self.timeout) as r:
            return r.read().decode("utf-8", "replace")

    # ---------- buildId ----------
    @property
    def build_id(self) -> str:
        """Next.js buildId (없으면 홈 HTML 에서 긁어와 캐시). _data() 가 URL 을 만들 때 쓴다."""
        if self._build_id is None:
            self._build_id = self._fetch_build_id()
        return self._build_id

    def _fetch_build_id(self) -> str:
        """홈 HTML 안의 "buildId":"..." 문자열을 정규식으로 찾는다."""
        html = self._get(BASE + "/")
        m = re.search(r'"buildId":"([^"]+)"', html)
        if not m:
            raise RuntimeError("buildId를 찾지 못함 (사이트 구조 변경 가능성)")
        return m.group(1)

    def _data(self, route: str, params: dict) -> dict:
        """/_next/data/{buildId}/{route}.json 호출. buildId 만료(404) 시 1회 재시도."""
        # 404 = 사이트가 재배포되어 buildId 가 바뀐 경우 → 캐시 비우고 한 번 더
        for attempt in range(2):
            url = f"{BASE}/_next/data/{self.build_id}/{route}.json?{urlencode(params)}"
            try:
                body = self._get(url, {"x-nextjs-data": "1"})
            except HTTPError as e:
                if e.code == 404 and attempt == 0:
                    self._build_id = None   # 배포되며 buildId 바뀜 -> 갱신 후 재시도
                    continue
                raise
            return json.loads(body)["pageProps"]
        raise RuntimeError("데이터 조회 실패")

    # ---------- 검색 ----------
    def search_page(
        self,
        keyword: str,
        check_in: str,          # "2026-09-05"
        check_out: str,         # "2026-09-06"
        personal: int = 2,
        page: int = 1,
        sort_type: str = "RECOMMEND",
        extra: dict | None = None,
    ) -> tuple[list[Hotel], dict]:
        """검색 결과 한 페이지를 (Hotel 목록, 페이지 정보) 로 돌려준다. search() 가 페이지마다 호출."""
        params = {
            "keyword": keyword,
            "checkIn": check_in,
            "checkOut": check_out,
            "personal": personal,
            "sortType": sort_type,
            "page": page,
        }
        if extra:
            params.update(extra)
        # pageProps 안의 accommodationsData 를 Hotel 로 변환, paginationInfo 는 다음 페이지 판단용
        pp = self._data("domestic-accommodations", params)
        items = [Hotel.from_raw(a) for a in (pp.get("accommodationsData") or [])]
        return items, (pp.get("paginationInfo") or {})

    def search(self, keyword: str, check_in: str, check_out: str,
               personal: int = 2, sort_type: str = "RECOMMEND",
               max_pages: int = 3) -> list[Hotel]:
        """여러 페이지를 자동으로 이어서 수집."""
        out: list[Hotel] = []
        page = 1
        # 결과가 비거나 마지막 페이지에 닿거나 max_pages 에 도달하면 멈춘다
        while page <= max_pages:
            items, pag = self.search_page(keyword, check_in, check_out,
                                          personal, page, sort_type)
            if not items:
                break
            out.extend(items)
            if page >= (pag.get("totalPageCount") or 1):
                break
            page += 1
            time.sleep(self.delay)
        return out

    # ---------- 상세 ----------
    def detail(self, accommodation_id: int, check_in: str, check_out: str,
               personal: int = 2) -> dict:
        """숙소 상세 페이지 데이터(pageProps 전체). room_options() 가 객실 정보를 꺼낼 때 쓴다."""
        return self._data(
            f"domestic-accommodations/{accommodation_id}",
            {"accommodationId": accommodation_id, "checkIn": check_in,
             "checkOut": check_out, "personal": personal},
        )

    # ---------- 객실 옵션 ----------
    def room_options(self, accommodation_id: int, check_in: str, check_out: str,
                     personal: int = 2) -> list[RoomOption]:
        """해당 날짜의 모든 객실 × (대실/숙박) 옵션을 평퀈4해서 반환."""
        info = self.detail(accommodation_id, check_in, check_out,
                           personal).get("accommodationInfo") or {}
        out: list[RoomOption] = []
        # 객실마다 rent(대실)/stay(숙박) 두 종류를 각각 RoomOption 한 개로 펼친다
        for r in info.get("rooms") or []:
            for kind, ctype in (("rent", RENT), ("stay", STAY)):
                o = r.get(kind)
                if not o:
                    continue
                price = (o.get("price") or {})
                label = (o.get("label") or {}).get("checkInOut")
                hours = None
                # 대실이면 라벨의 'N시간' 에서 최대 이용시간을 뽑는다
                if kind == "rent" and label:
                    m = re.search(r"(\d+)\s*시간", label)
                    hours = int(m.group(1)) if m else None
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
                    max_hours=hours,
                ))
        return out

    def find_rent(self, accommodation_id: int, date: str, personal: int = 2,
                  cheapest: bool = True) -> RoomOption | None:
        """특정 날짜에 예약 가능한 대실 객실 찾기."""
        nxt = _next_day(date)
        opts = [o for o in self.room_options(accommodation_id, date, nxt, personal)
                if o.kind == "rent" and o.available]
        if not opts:
            return None
        return min(opts, key=lambda o: o.price) if cheapest else opts[0]


def _next_day(d: str) -> str:
    """YYYY-MM-DD 문자열의 다음 날. find_rent() 가 대실 체크아웃 날짜 계산에 쓴다."""
    from datetime import date as _d, timedelta
    y, m, dd = map(int, d.split("-"))
    return (_d(y, m, dd) + timedelta(days=1)).isoformat()


def rent_slots(open_from: str = "14:00", open_to: str = "20:00",
               step_min: int = 30) -> list[str]:
    """체크아웃 페이지에 나오는 대실 입실시각 슬롯(30분 간격). 실제 목록은 숨소마다 다름."""
    # 시:분 → 분 단위 정수로 바꿔 step_min 씩 더하며 라벨을 만든다
    h1, m1 = map(int, open_from.split(":"))
    h2, m2 = map(int, open_to.split(":"))
    cur, end, out = h1 * 60 + m1, h2 * 60 + m2, []
    while cur <= end:
        out.append(f"{cur // 60:02d}:{cur % 60:02d}")
        cur += step_min
    return out


def plan_rent(opt: RoomOption, start: str, end: str) -> dict:
    """원하는 대실 시간대가 가능한지 검증하고 선택할 슬롯을 돌려준다.

    여기어때 대실은 '입실시각'만 고르면 퇴실은 입실+최대이용시간으로 자동 계산된다.
    """
    # 요청 시간대 길이(분)를 구해 객실 최대 이용시간과 비교
    sh, sm = map(int, start.split(":"))
    eh, em = map(int, end.split(":"))
    dur_min = (eh * 60 + em) - (sh * 60 + sm)
    if dur_min <= 0:
        raise ValueError("종료시각이 시작시각보다 빨라요")
    max_min = (opt.max_hours or 0) * 60
    if max_min and dur_min > max_min:
        raise ValueError(
            f"요청 {dur_min//60}시간{dur_min%60}분 > 이 객실 최대 {opt.max_hours}시간")
    auto_end_min = sh * 60 + sm + max_min
    return {
        "slot": start,                      # 체크아웃에서 클릭할 버튼 라벨
        "requested": f"{start}~{end}",
        "actual": f"{start}~{auto_end_min//60:02d}:{auto_end_min%60:02d}",
        "max_hours": opt.max_hours,
        "price": opt.price,
    }


if __name__ == "__main__":
    import argparse

    # 단독 실행용 CLI: 키워드/체크인/체크아웃을 받아 검색 결과를 표 또는 JSON 으로 출력
    ap = argparse.ArgumentParser(description="여기어때 숙소 검색")
    ap.add_argument("keyword")
    ap.add_argument("check_in")
    ap.add_argument("check_out")
    ap.add_argument("-p", "--personal", type=int, default=2)
    ap.add_argument("-s", "--sort", default="LOWPRICE", choices=list(SORT_TYPES))
    ap.add_argument("-n", "--pages", type=int, default=1)
    ap.add_argument("--json", action="store_true", help="JSON으로 출력")
    args = ap.parse_args()

    y = Yeogi()
    rows = y.search(args.keyword, args.check_in, args.check_out,
                    args.personal, args.sort, args.pages)

    if args.json:
        print(json.dumps([asdict(h) for h in rows], ensure_ascii=False, indent=2))
    else:
        print(f"[{args.keyword}] {args.check_in}~{args.check_out} "
              f"{args.personal}인 · {SORT_TYPES[args.sort]} · {len(rows)}건\n")
        for h in rows:
            price = f"{h.stay_price:,}원" if h.stay_price else "-"
            print(f"{price:>12}  ★{h.rating or '-':<4} ({h.review_count or 0:,})  "
                  f"[{h.grade}] {h.name}  {h.traffic or ''}")
