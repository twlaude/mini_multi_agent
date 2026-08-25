# seed.py — 주차 출입 시스템 가짜 데이터 시딩 (plan_db.md 4절이 원본)
# 실행: pip install "psycopg[binary]" && python db/seed.py
# 여러 번 실행해도 안전 (매번 전체 truncate 후 다시 채움).
#
# 시딩 시나리오 (데모 대본이기도 하다):
#   기능① 외부인 조회   → 11하1111, 22호2222 가 지금 주차중인 외부인 (정답 2대)
#   기능② 음주 체크     → 12가3456 은 평소 19시경 출차 (새벽/낮 출차 시도 = 이상 시간대)
#   기능③ 꼬리물기 탐지 → 99허9999 가 게이트 기록 없이 A-13 자리에 등장 (정답 1대)

import datetime as dt
import random

DSN = "postgresql://parking:parking@localhost:5432/parking"

try:
    import psycopg  # psycopg 3
except ImportError:  # 구형 환경 폴백 — API 사용 범위가 같아서 그대로 동작
    import psycopg2 as psycopg

random.seed(42)  # 팀원 컴에서도 같은 데이터가 나오게 고정

KST = dt.timezone(dt.timedelta(hours=9))
TODAY = dt.datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0)

# ── 차량 명단 ──────────────────────────────────────────────
# (plate, owner, type, 평소출차시각h, 평소입차시각h)  — 시각 None = 이력 안 만듦
REGISTERED = [
    ("12가3456", "김민준", "resident", 19, 8),   # 야간 근무자: 아침 입차, 저녁 출차 ← 음주체크 데모 주인공
    ("34나5678", "이서연", "resident", 8, 19),   # 평범한 출퇴근
    ("56다7890", "박지훈", "resident", 8, 19),
    ("78라1234", "최수아", "resident", 9, 18),
    ("90마5678", "정도윤", "staff",    7, 16),
    ("23바9012", "강하은", "resident", 8, 20),
    ("45사3456", "윤시우", "resident", None, None),  # 장기 주차족 — 이력 5건 미만
    ("67아7890", "임유나", "resident", None, None),  # 등록만 하고 거의 안 옴
]
VISITORS_PARKED = ["11하1111", "22호2222"]   # 오늘 정상 입차한 외부인 (기능① 정답)
VISITOR_GONE = "33배3333"                     # 어제 왔다 간 외부인
TAILGATER = "99허9999"                        # 꼬리물기 (기능③ 정답)

# 지금 주차중인 차 → 자리 배정 (마지막 게이트 이벤트가 enter 여야 함)
PARKED_NOW = {
    "12가3456": "A-01",   # 오늘 아침 입차, 저녁에 나갈 차
    "78라1234": "A-02",   # 오늘 휴무라 안 나감
    "90마5678": "A-03",
    "45사3456": "A-04",   # 3일째 장기 주차
    "11하1111": "A-15",
    "22호2222": "A-16",
}


def jitter(hour, spread_min=25):
    """hour시 ±spread_min분 근처의 시각(분 단위)을 돌려준다"""
    return dt.timedelta(hours=hour, minutes=random.randint(-spread_min, spread_min))


def main():
    conn = psycopg.connect(DSN)
    cur = conn.cursor()

    cur.execute("""
        truncate vehicles, gate_events, parking_spots, spot_events,
                 sobriety_checks, alerts restart identity cascade
    """)

    # 1. 주차면 20개
    for i in range(1, 21):
        cur.execute("insert into parking_spots (spot_id) values (%s)", (f"A-{i:02d}",))

    # 2. 등록 차량
    for plate, owner, vtype, _, _ in REGISTERED:
        cur.execute(
            "insert into vehicles (plate, owner_name, vehicle_type) values (%s,%s,%s)",
            (plate, owner, vtype),
        )

    def gate(plate, direction, ts, reason="정상 통행"):
        cur.execute(
            """insert into gate_events (plate, direction, decision, reason, mode, created_at)
               values (%s,%s,'open',%s,'workflow',%s)""",
            (plate, direction, reason, ts),
        )

    def spot(spot_id, plate, event, ts):
        cur.execute(
            """insert into spot_events (spot_id, plate, event, created_at)
               values (%s,%s,%s,%s)""",
            (spot_id, plate, event, ts),
        )

    # 3. 지난 30일 입출차 이력 (패턴 있는 6대) — 기능②의 "평소 출차 시간대" 근거
    for plate, _, _, exit_h, enter_h in REGISTERED:
        if exit_h is None:
            continue
        for d in range(30, 0, -1):  # 30일 전 ~ 어제
            day = TODAY - dt.timedelta(days=d)
            if random.random() < 0.12:  # 가끔 쉬는 날
                continue
            ts_exit = day + jitter(exit_h)
            ts_enter = day + jitter(enter_h)
            # 시간순으로 기록 (출차가 먼저인 사람 / 입차가 먼저인 사람)
            for ts, direction in sorted([(ts_exit, "exit"), (ts_enter, "enter")]):
                gate(plate, direction, ts)

    # 4. 오늘의 현재 상태 만들기
    #    - 출퇴근조(34나/56다/23바)는 오늘 아침 출차 → 지금 주차장에 없음
    for plate in ["34나5678", "56다7890", "23바9012"]:
        gate(plate, "exit", TODAY + jitter(8))
    #    - 지금 주차중인 등록 차량: 마지막 이벤트가 enter 가 되도록 오늘(또는 3일 전) 입차
    gate("12가3456", "enter", TODAY + jitter(8))            # 야간 근무자 아침 복귀
    gate("78라1234", "enter", TODAY - dt.timedelta(days=1) + jitter(18))  # 어젯밤 입차 후 휴무
    gate("90마5678", "enter", TODAY - dt.timedelta(days=1) + jitter(16))
    gate("45사3456", "enter", TODAY - dt.timedelta(days=3) + jitter(14))  # 장기 주차
    #    - 외부인: 오늘 정상 입차 2대 + 어제 왔다 간 1대
    gate("11하1111", "enter", TODAY + dt.timedelta(hours=10, minutes=12), "방문 차량 입차")
    gate("22호2222", "enter", TODAY + dt.timedelta(hours=11, minutes=40), "방문 차량 입차")
    gate(VISITOR_GONE, "enter", TODAY - dt.timedelta(days=1) + dt.timedelta(hours=13))
    gate(VISITOR_GONE, "exit", TODAY - dt.timedelta(days=1) + dt.timedelta(hours=15))

    # 5. 자리 센서: 주차중인 차들 자리에 앉히기
    for plate, spot_id in PARKED_NOW.items():
        # 입차 시각보다 몇 분 뒤에 자리에 도착한 것으로
        cur.execute(
            "select max(created_at) from gate_events where plate=%s and direction='enter'",
            (plate,),
        )
        entered = cur.fetchone()[0]
        spot(spot_id, plate, "occupied", entered + dt.timedelta(minutes=random.randint(2, 6)))

    # 6. 꼬리물기: 게이트 기록 없이 자리에만 등장 (기능③ 정답)
    spot("A-13", TAILGATER, "occupied", TODAY + dt.timedelta(hours=14, minutes=5))

    conn.commit()

    # ── 검증 3종 (plan_db.md 완료 기준) ──────────────────────
    # ① 지금 주차중인 외부인 = 정확히 2대
    cur.execute("""
        with last_gate as (
            select distinct on (plate) plate, direction
            from gate_events order by plate, created_at desc
        )
        select plate from last_gate
        where direction = 'enter' and plate not in (select plate from vehicles)
        order by plate
    """)
    visitors = [r[0] for r in cur.fetchall()]
    assert visitors == sorted(VISITORS_PARKED), f"외부인 조회 실패: {visitors}"

    # ② 12가3456 평균 출차 시각 = 19시대
    cur.execute("""
        select avg(extract(hour from created_at at time zone 'Asia/Seoul'))
        from gate_events where plate='12가3456' and direction='exit'
    """)
    avg_h = float(cur.fetchone()[0])
    assert 18.4 <= avg_h <= 19.6, f"평소 출차시각 비정상: {avg_h:.2f}시"

    # ③ 꼬리물기 후보 = 99허9999 하나
    cur.execute("""
        select distinct s.plate from spot_events s
        where s.event = 'occupied'
          and not exists (
            select 1 from gate_events g
            where g.plate = s.plate and g.direction = 'enter'
              and g.created_at between s.created_at - interval '24 hours' and s.created_at
          )
    """)
    tailgaters = [r[0] for r in cur.fetchall()]
    assert tailgaters == [TAILGATER], f"꼬리물기 탐지 실패: {tailgaters}"

    cur.execute("select count(*) from gate_events")
    n_gate = cur.fetchone()[0]
    print(f"✅ 시딩 완료: gate_events {n_gate}건, 주차중 {len(PARKED_NOW)}대, "
          f"외부인 {visitors}, 꼬리물기 {tailgaters}, 12가3456 평균출차 {avg_h:.1f}시")
    conn.close()


if __name__ == "__main__":
    main()
