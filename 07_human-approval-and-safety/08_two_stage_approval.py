"""여행 AI Agent가 서로 다른 두 변경 단계에서 각각 승인을 받는 예제입니다.

상황:
사용자가 "제주 여행 일정을 만들고 적절한 호텔도 예약해 줘"라고 요청합니다.
Agent는 여행 일정과 호텔 예약안을 준비할 수 있지만, 일정 저장과 호텔 예약은 서로
다른 외부 변경입니다. 따라서 한 번의 승인으로 두 작업을 모두 실행하지 않습니다.

실행 흐름:
여행 일정 초안 생성
→ 1차 승인: 이 일정을 저장할 것인가?
   ├─ y: SQLite Database에 일정 저장
   └─ n: 아무것도 저장하지 않고 종료
→ 호텔 예약안 생성
→ 2차 승인: 이 호텔을 실제로 예약할 것인가?
   ├─ y: Mock 호텔 예약 실행 후 Database에 결과 기록
   └─ n: 저장된 일정은 유지하고 호텔 예약만 취소

이 예제의 목적은 승인 횟수를 무조건 늘리는 것이 아닙니다. 서로 다른 Side Effect가
발생하는 시점마다 사용자가 구체적인 대상을 확인하고 결정하게 하는 것이 핵심입니다.
첫 번째 변경은 실제 SQLite에 저장하고, 외부 호텔 API가 필요한 두 번째 변경은 Mock
예약으로 처리합니다. 다음 행동은 학습용 Python 규칙이 선택하며 LLM 기반 Agent에서도
동일한 승인 State와 실행 경계를 적용할 수 있습니다.
"""

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


Status = Literal[
    "running",
    "waiting_itinerary_approval",
    "waiting_booking_approval",
    "completed",
    "rejected",
]

DEFAULT_DB_PATH = Path(__file__).with_name("travel_agent.db")


@dataclass
class TravelState:
    """두 번의 승인 사이에서 유지할 최소한의 여행 실행 State입니다."""

    run_id: str
    user_id: str
    city: str
    status: Status = "running"
    itinerary: dict | None = None
    booking: dict | None = None


def initialize_database(db_path: Path) -> None:
    """일정과 Mock 호텔 예약 결과를 저장할 SQLite Table을 준비합니다."""

    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS itineraries (
                run_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                city TEXT NOT NULL,
                place TEXT NOT NULL,
                weather TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS bookings (
                run_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                hotel TEXT NOT NULL,
                check_in TEXT NOT NULL,
                check_out TEXT NOT NULL,
                guests INTEGER NOT NULL,
                total_price INTEGER NOT NULL,
                status TEXT NOT NULL
            );
            """
        )


def create_itinerary(state: TravelState) -> dict:
    """날씨와 장소를 조회했다고 가정하고 첫 번째 승인 대상을 만듭니다."""

    state.itinerary = {
        "city": state.city,
        "place": "비자림",
        "weather": "비",
    }
    state.status = "waiting_itinerary_approval"
    return state.itinerary


def save_itinerary(state: TravelState, db_path: Path) -> None:
    """1차 승인된 여행 일정을 run_id별로 한 번만 Database에 저장합니다."""

    if state.status != "waiting_itinerary_approval" or not state.itinerary:
        raise ValueError("일정 승인 대기 상태가 아닙니다.")

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO itineraries
                (run_id, user_id, city, place, weather)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                state.run_id,
                state.user_id,
                state.itinerary["city"],
                state.itinerary["place"],
                state.itinerary["weather"],
            ),
        )


def create_booking_draft(state: TravelState) -> dict:
    """일정 저장 후 사용자가 별도로 승인할 호텔 예약안을 만듭니다."""

    state.booking = {
        "hotel": "제주 숲 호텔",
        "check_in": "2026-09-10",
        "check_out": "2026-09-12",
        "guests": 2,
        "total_price": 280_000,
        "cancellation_policy": "체크인 3일 전까지 전액 환불",
    }
    state.status = "waiting_booking_approval"
    return state.booking


def book_hotel(state: TravelState, db_path: Path) -> dict:
    """2차 승인 후 Mock 호텔 예약을 실행하고 그 결과를 Database에 기록합니다."""

    if state.status != "waiting_booking_approval" or not state.booking:
        raise ValueError("호텔 예약 승인 대기 상태가 아닙니다.")

    result = {"reservation_id": f"mock-{state.run_id}", "status": "booked"}
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO bookings
                (run_id, user_id, hotel, check_in, check_out, guests, total_price, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                state.run_id,
                state.user_id,
                state.booking["hotel"],
                state.booking["check_in"],
                state.booking["check_out"],
                state.booking["guests"],
                state.booking["total_price"],
                result["status"],
            ),
        )
    state.status = "completed"
    return result


def ask_approval(question: str) -> bool:
    """터미널에서 사용자가 y 또는 n을 입력할 때까지 승인을 요청합니다."""

    while True:
        answer = input(f"{question} [y/n]: ").strip().lower()
        if answer in {"y", "yes", "승인"}:
            return True
        if answer in {"n", "no", "거절"}:
            return False
        print("y(승인) 또는 n(거절)을 입력해 주세요.")


def main(db_path: Path = DEFAULT_DB_PATH) -> None:
    """두 승인 지점과 각 거절 경로를 순서대로 실행합니다."""

    initialize_database(db_path)
    state = TravelState(run_id="jeju-20260910", user_id="user-01", city="제주")

    itinerary = create_itinerary(state)
    print("\n1차 승인 대상 - 여행 일정")
    print(itinerary)

    if not ask_approval("이 여행 일정을 Database에 저장할까요?"):
        state.status = "rejected"
        print("일정을 저장하지 않고 종료합니다.")
        return

    save_itinerary(state, db_path)
    print("일정을 Database에 저장했습니다.")

    booking = create_booking_draft(state)
    print("\n2차 승인 대상 - 호텔 예약")
    for key, value in booking.items():
        print(f"{key}: {value}")

    if not ask_approval("이 호텔을 예약할까요?"):
        state.status = "rejected"
        print("호텔은 예약하지 않았습니다. 저장된 여행 일정은 유지됩니다.")
        return

    result = book_hotel(state, db_path)
    print("호텔 예약을 완료했습니다:", result)


if __name__ == "__main__":
    main()
