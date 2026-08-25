from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.db import get_conn
from app.domains.parking_workflow.schemas import GateRequest


KST = ZoneInfo("Asia/Seoul")


def _kst_time(at: datetime | None) -> datetime:
    if at is None:
        return datetime.now(KST)
    if at.tzinfo is None:
        return at.replace(tzinfo=KST)
    return at.astimezone(KST)


def _decision(decision: str, reason: str, check_id: int | None = None) -> dict:
    return {"decision": decision, "reason": reason, "mode": "workflow", "check_id": check_id}


def evaluate_gate(plate: str, direction: str, at: datetime | None = None) -> dict:
    """고정 룰을 평가한다. gate_events 기록은 process_gate만 담당한다."""
    event_at = _kst_time(at)
    with get_conn() as conn:
        if direction == "enter":
            registered = conn.execute(
                "select 1 from vehicles where plate = %s", (plate,)
            ).fetchone()
            reason = "등록 차량" if registered else "외부인 입차 — 방문 기록"
            return _decision("open", reason)
        if direction != "exit":
            raise ValueError("direction은 enter 또는 exit여야 합니다.")

        history = conn.execute(
            """
            select count(*) as count,
                   avg(extract(hour from created_at at time zone 'Asia/Seoul')) as avg_hour,
                   stddev_samp(extract(hour from created_at at time zone 'Asia/Seoul')) as stddev_hour
            from gate_events
            where plate = %s and direction = 'exit' and decision = 'open'
              and created_at >= %s - interval '30 days' and created_at < %s
            """,
            (plate, event_at, event_at),
        ).fetchone()
        if history["count"] < 5:
            return _decision("open", "룰1: 최근 30일 출차 이력 5건 미만 → 정상 출차")

        avg_hour = float(history["avg_hour"])
        current_hour = event_at.hour + event_at.minute / 60
        unusual = event_at.hour <= 5 or abs(current_hour - avg_hour) > 2
        if not unusual:
            return _decision("open", "룰1: 평소 출차 시간대 → 정상 출차")

        prefix = f"룰2: 평소 {int(avg_hour + 0.5):02d}시 출차, 현재 {event_at.hour:02d}시"
        resolved = conn.execute(
            """
            select id, status from sobriety_checks
            where plate = %s and status in ('pass', 'fail')
              and requested_at between %s - interval '1 hour' and %s
            order by requested_at desc, id desc limit 1
            """,
            (plate, event_at, event_at),
        ).fetchone()
        if resolved and resolved["status"] == "pass":
            return _decision("open", f"{prefix} → 음주측정 통과", resolved["id"])
        if resolved:
            conn.execute(
                """
                insert into alerts (alert_type, plate, detail, created_at)
                select 'drunk_suspect', %s, %s, %s
                where not exists (
                    select 1 from alerts
                    where alert_type = 'drunk_suspect' and plate = %s
                      and resolved = false
                )
                """,
                (plate, f"{prefix} → 음주측정 실패", event_at, plate),
            )
            return _decision("deny", f"{prefix} → 음주측정 실패", resolved["id"])

        pending = conn.execute(
            """
            select id from sobriety_checks
            where plate = %s and status = 'pending'
              and requested_at between %s - interval '1 hour' and %s
            order by requested_at desc, id desc limit 1
            """,
            (plate, event_at, event_at),
        ).fetchone()
        if pending:
            check_id = pending["id"]
        else:
            check_id = conn.execute(
                """insert into sobriety_checks (plate, requested_at)
                   values (%s, %s) returning id""",
                (plate, event_at),
            ).fetchone()["id"]
        return _decision("hold", f"{prefix} → 음주측정 대기", check_id)


def process_gate(payload: GateRequest) -> dict:
    event_at = _kst_time(payload.at)
    result = evaluate_gate(payload.plate, payload.direction, event_at)
    with get_conn() as conn:
        conn.execute(
            """
            insert into gate_events
                (plate, direction, decision, reason, mode, created_at)
            values (%s, %s, %s, %s, 'workflow', %s)
            """,
            (
                payload.plate,
                payload.direction,
                result["decision"],
                result["reason"],
                event_at,
            ),
        )
    return result


def list_visitors() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            with last_gate as (
                select distinct on (plate) plate, direction, decision,
                       created_at, id
                from gate_events
                order by plate, created_at desc, id desc
            ), last_spot as (
                select distinct on (plate) plate, spot_id, event
                from spot_events
                order by plate, created_at desc, id desc
            )
            select g.plate, g.created_at as entered_at,
                   case when s.event = 'occupied' then s.spot_id end as spot_id
            from last_gate g
            left join vehicles v on v.plate = g.plate
            left join last_spot s on s.plate = g.plate
            where g.direction = 'enter' and g.decision = 'open'
              and v.plate is null
            order by g.created_at desc
            """
        ).fetchall()
    return [dict(row) for row in rows]


def list_tailgating() -> list[dict]:
    with get_conn() as conn:
        conn.execute(
            """
            insert into alerts (alert_type, plate, detail, created_at)
            select distinct on (s.plate) 'tailgating', s.plate,
                   s.spot_id || '에서 게이트 입차 없이 점유 감지', s.created_at
            from spot_events s
            where s.event = 'occupied' and not exists (
                select 1 from gate_events g where g.plate = s.plate
                  and g.direction = 'enter' and g.decision = 'open'
                  and g.created_at between s.created_at - interval '24 hours'
                                           and s.created_at
            ) and not exists (
                select 1 from alerts a where a.plate = s.plate
                  and a.alert_type = 'tailgating' and a.resolved = false
            )
            order by s.plate, s.created_at desc
            """
        )
        rows = conn.execute(
            """
            with candidates as (
                select s.plate, s.spot_id, s.created_at as observed_at
                from spot_events s
                where s.event = 'occupied' and not exists (
                    select 1 from gate_events g
                    where g.plate = s.plate and g.direction = 'enter'
                      and g.decision = 'open'
                      and g.created_at between
                          s.created_at - interval '24 hours' and s.created_at
                )
                union all
                select a.plate, s.spot_id,
                       coalesce(s.created_at, a.created_at) as observed_at
                from alerts a
                left join lateral (
                    select spot_id, created_at from spot_events
                    where plate = a.plate and event = 'occupied'
                    order by created_at desc, id desc limit 1
                ) s on true
                where a.alert_type = 'tailgating' and a.resolved = false
            )
            select distinct on (plate) plate, spot_id, observed_at
            from candidates
            order by plate, observed_at desc
            """
        ).fetchall()
    return [dict(row) for row in rows]
