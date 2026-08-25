"""추가 시나리오 시딩 (멱등) — 데모 화면이 심심하지 않게 내부인·외부인·꼬리물기 차량을 더 넣는다.

실행: PARKING_DSN=postgresql://parking:parking@localhost:5435/parking python3 db/seed_extra.py
- 내부인 주차 +3: 34나5678(A-05) 56다7890(A-06) 23바9012(A-07) — 오늘 아침 정상 입차 + 자리 점유
- 외부인 주차 +2: 33배3333(A-17) 55보5555(A-18) — 오늘 정상 입차(방문) + 자리 점유
- 꼬리물기 +2: 88허8888(A-19) 77호7777(A-20) — 게이트 입차 기록 없이 자리에만 등장
"""

import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg

KST = ZoneInfo("Asia/Seoul")
DSN = os.environ.get("PARKING_DSN", "postgresql://parking:parking@localhost:5435/parking")
today = datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0)

RESIDENTS = [("34나5678", "A-05", 7, 52), ("56다7890", "A-06", 8, 15), ("23바9012", "A-07", 8, 41)]
VISITORS = [("33배3333", "A-17", 9, 20), ("55보5555", "A-18", 9, 47)]
TAILGATERS = [("88허8888", "A-19", 9, 5), ("77호7777", "A-20", 9, 58)]


def occupied_now(conn, spot_id: str) -> bool:
    row = conn.execute(
        "select event from spot_events where spot_id = %s order by created_at desc, id desc limit 1",
        (spot_id,),
    ).fetchone()
    return bool(row and row[0] == "occupied")


def park(conn, plate: str, spot_id: str, at: datetime, with_gate: bool, reason: str) -> None:
    if occupied_now(conn, spot_id):
        print(f"  skip {plate} — {spot_id} 이미 점유")
        return
    if with_gate:
        conn.execute(
            """insert into gate_events (plate, direction, decision, reason, mode, created_at)
               values (%s, 'enter', 'open', %s, 'workflow', %s)""",
            (plate, reason, at),
        )
    conn.execute(
        "insert into spot_events (spot_id, plate, event, created_at) values (%s, %s, 'occupied', %s)",
        (spot_id, plate, at + timedelta(minutes=3)),
    )
    print(f"  {plate} → {spot_id} ({'게이트 입차 후' if with_gate else '게이트 기록 없음'})")


with psycopg.connect(DSN) as conn:
    print("내부인:")
    for plate, spot, h, m in RESIDENTS:
        park(conn, plate, spot, today.replace(hour=h, minute=m), True, "등록 차량")
    print("외부인:")
    for plate, spot, h, m in VISITORS:
        park(conn, plate, spot, today.replace(hour=h, minute=m), True, "외부인 입차 — 방문 기록")
    print("꼬리물기:")
    for plate, spot, h, m in TAILGATERS:
        park(conn, plate, spot, today.replace(hour=h, minute=m), False, "")
    conn.commit()
    occ = conn.execute(
        """select count(*) from parking_spots p join lateral (
             select event from spot_events where spot_id = p.spot_id
             order by created_at desc, id desc limit 1) l on true where l.event = 'occupied'"""
    ).fetchone()[0]
    print(f"점유 주차면: {occ}/20")
