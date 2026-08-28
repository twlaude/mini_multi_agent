"""여기어때(yeogi.com) 비공식 조회 클라이언트 — HTTP 계층.

원리:
  여기어때 웹은 Next.js(Pages Router) SSR. 검색 결과는 페이지 HTML의
  __NEXT_DATA__ 안에 통째로 들어있고, 같은 데이터를 아래 경로가 순수 JSON으로 뱉는다.

    GET https://www.yeogi.com/_next/data/{buildId}/domestic-accommodations.json?<검색쿼리>
    (헤더: x-nextjs-data: 1)

  buildId는 배포될 때마다 바뀌므로 https://www.yeogi.com/ HTML에서 매번 긁어온다.
  쿠키/로그인/토큰 전부 불필요. 브라우저도 불필요. 파이썬 표준 라이브러리만 사용.

주의: 공식 API 아님. 언제든 스펙이 바뀔 수 있고 과도한 호출은 차단 대상.
"""

import json
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.clients.base import AccommodationClient, SearchPage
from app.core.config import HotelSettings
from app.schemas import Hotel, RoomOption

from .parser import extract_build_id, parse_room_options, parse_search_page


# 숙소 유형 한글 이름 → 여기어때 검색 쿼리의 category 코드 (2026-08-27 실측: 1=모텔 2=호텔 3=펜션 5=캠핑, 없으면 전체)
CATEGORY_CODES = {"호텔": 2, "모텔": 1, "펜션": 3, "캠핑": 5}


class YeogiClient(AccommodationClient):
    """buildId 를 한 번 얻어 캐시하고, search_page / detail / room_options 로 조회한다.

    hotel_server.py 가 프로세스당 인스턴스 하나를 만들어 공유한다.
    """

    def __init__(self, settings: HotelSettings):
        self.settings = settings
        self._build_id: str | None = None

    def _get(self, url: str, headers: dict | None = None) -> str:
        """URL 을 GET 해서 본문 문자열을 돌려주는 최소 HTTP 도우미. 모든 요청이 거쳐 간다."""
        h = {"User-Agent": self.settings.user_agent, "Accept-Language": "ko-KR,ko;q=0.9"}
        h.update(headers or {})
        with urlopen(Request(url, headers=h), timeout=self.settings.request_timeout) as r:
            return r.read().decode("utf-8", "replace")

    # ---------- buildId ----------
    @property
    def build_id(self) -> str:
        """Next.js buildId (없으면 홈 HTML 에서 긁어와 캐시). _data() 가 URL 을 만들 때 쓴다."""
        if self._build_id is None:
            self._build_id = extract_build_id(self._get(self.settings.base_url + "/"))
        return self._build_id

    def _data(self, route: str, params: dict) -> dict:
        """/_next/data/{buildId}/{route}.json 호출. buildId 만료(404) 시 1회 재시도."""
        # 404 = 사이트가 재배포되어 buildId 가 바뀐 경우 → 캐시 비우고 한 번 더
        for attempt in range(2):
            url = f"{self.settings.base_url}/_next/data/{self.build_id}/{route}.json?{urlencode(params)}"
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
        category: str | None = None,
    ) -> SearchPage:
        """검색 결과 한 페이지. category 코드는 검색 쿼리에 실어 여기어때 쪽에서 걸러 받는다 (한 페이지 20건)."""
        params = {
            "keyword": keyword,
            "checkIn": check_in,
            "checkOut": check_out,
            "personal": personal,
            "sortType": sort_type,
            "page": page,
        }
        if category in CATEGORY_CODES:
            params["category"] = CATEGORY_CODES[category]
        return parse_search_page(self._data("domestic-accommodations", params), self.settings.base_url)

    # ---------- 상세 / 객실 ----------
    def detail(self, accommodation_id: int, check_in: str, check_out: str,
               personal: int = 2) -> dict:
        """숙소 상세 페이지 데이터(pageProps 전체)."""
        return self._data(
            f"domestic-accommodations/{accommodation_id}",
            {"accommodationId": accommodation_id, "checkIn": check_in,
             "checkOut": check_out, "personal": personal},
        )

    def room_options(self, accommodation_id: int, check_in: str, check_out: str,
                     personal: int = 2) -> list[RoomOption]:
        """해당 날짜의 모든 객실 × (대실/숙박) 옵션."""
        return parse_room_options(
            self.detail(accommodation_id, check_in, check_out, personal), accommodation_id
        )
