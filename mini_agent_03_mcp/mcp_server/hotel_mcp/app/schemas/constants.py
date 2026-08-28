"""여기어때 도메인 상수 — 체크인 유형, 정렬, 숙소 유형."""

from typing import Literal


# 체크아웃 URL의 checkinType
RENT = 1   # 대실 (시간단위, 체크아웃페이지에서 입실시각 선택)
STAY = 2   # 숙박 (1박 이상, 입/퇴실 시각 고정)

# 정렬 옵션 코드 → 한글 의미. SortType Literal 과 yeogi://sort-types Resource 가 참조
SORT_TYPES = {
    "RECOMMEND": "추천순",
    "HI_MEMBERSHIP_DISCOUNT": "할인율 높은순",
    "HIRATING": "평점높은순",
    "HIREVIEW": "리뷰많은순",
    "LOWPRICE": "낮은가격순",
    "HIPRICE": "높은가격순",
    "DISTANCE": "거리순",
}

# Literal 로 두면 FastMCP 가 enum 으로 스키마에 넣어 GPT 가 허용값을 알게 된다
SortType = Literal[
    "RECOMMEND", "LOWPRICE", "HIPRICE", "HIRATING", "HIREVIEW",
    "HI_MEMBERSHIP_DISCOUNT", "DISTANCE",
]

# 숙소 유형 (사이트별 코드 변환은 각 client 가 담당 — clients/yeogi/client.py CATEGORY_CODES)
Category = Literal["전체", "호텔", "모텔", "펜션", "캠핑"]
