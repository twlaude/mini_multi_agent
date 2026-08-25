import httpx

from app.config import settings
from app.core.db import get_conn, ping_db


class ParkingServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def record_spot_event(spot_id: str, plate: str, event: str) -> dict:
    with get_conn() as conn:
        spot = conn.execute(
            "select 1 as found from parking_spots where spot_id = %s", (spot_id,)
        ).fetchone()
        if spot is None:
            raise ParkingServiceError("주차면을 찾을 수 없습니다.", 404)
        row = conn.execute(
            """insert into spot_events (spot_id, plate, event)
               values (%s, %s, %s)
               returning id, spot_id, plate, event, created_at""",
            (spot_id, plate, event),
        ).fetchone()
        alert_created = False
        if event == "occupied":
            entered = conn.execute(
                """select exists (
                       select 1 from gate_events
                       where plate = %s and direction = 'enter'
                         and decision = 'open'
                         and created_at between %s - interval '24 hours' and %s
                   ) as found""",
                (plate, row["created_at"], row["created_at"]),
            ).fetchone()["found"]
            if not entered:
                conn.execute(
                    "select pg_advisory_xact_lock(hashtext(%s))", (plate,)
                )
                inserted = conn.execute(
                    """insert into alerts (alert_type, plate, detail)
                       select 'tailgating', %s, %s
                       where not exists (
                           select 1 from alerts
                           where alert_type = 'tailgating'
                             and plate = %s and resolved = false
                       ) returning id""",
                    (plate, f"{spot_id}에서 게이트 입차 없이 점유 감지", plate),
                ).fetchone()
                alert_created = inserted is not None
    return {**dict(row), "alert_created": alert_created}


def resolve_sobriety_check(check_id: int, result: str) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            """update sobriety_checks
               set status = %s, resolved_at = now()
               where id = %s and status = 'pending'
               returning id, plate, status, requested_at, resolved_at""",
            (result, check_id),
        ).fetchone()
        if row is None:
            exists = conn.execute(
                "select status from sobriety_checks where id = %s", (check_id,)
            ).fetchone()
            if exists is None:
                raise ParkingServiceError("음주측정 요청을 찾을 수 없습니다.", 404)
            raise ParkingServiceError("이미 처리된 음주측정 요청입니다.", 409)
        alert_created = False
        if result == "fail":
            conn.execute(
                "select pg_advisory_xact_lock(hashtext(%s))", (row["plate"],)
            )
            inserted = conn.execute(
                """insert into alerts (alert_type, plate, detail)
                   select 'drunk_suspect', %s, '음주측정 실패'
                   where not exists (
                       select 1 from alerts
                       where alert_type = 'drunk_suspect'
                         and plate = %s and resolved = false
                   ) returning id""",
                (row["plate"], row["plate"]),
            ).fetchone()
            alert_created = inserted is not None
    return {**dict(row), "alert_created": alert_created}


def get_parking_status() -> dict:
    with get_conn() as conn:
        spots = conn.execute(
            """select p.spot_id, p.floor,
                      case when latest.event = 'occupied' then latest.plate end as plate,
                      coalesce(latest.event = 'occupied', false) as occupied
               from parking_spots p
               left join lateral (
                   select plate, event from spot_events
                   where spot_id = p.spot_id
                   order by created_at desc, id desc limit 1
               ) latest on true
               order by p.spot_id"""
        ).fetchall()
        events = conn.execute(
            """select id, plate, direction, decision, reason, mode, created_at
               from gate_events order by created_at desc, id desc limit 20"""
        ).fetchall()
        checks = conn.execute(
            """select id, plate, status, requested_at
               from sobriety_checks where status = 'pending'
               order by requested_at desc, id desc"""
        ).fetchall()
        alerts = conn.execute(
            """select id, alert_type, plate, detail, created_at
               from alerts where resolved = false
               order by created_at desc, id desc"""
        ).fetchall()
    return {
        "spots": [dict(row) for row in spots],
        "recent_events": [dict(row) for row in events],
        "sobriety_checks": [dict(row) for row in checks],
        "alerts": [dict(row) for row in alerts],
    }


def get_health() -> dict[str, str]:
    try:
        db_status = "ok" if ping_db() else "error"
    except Exception:
        db_status = "error"
    try:
        response = httpx.get(f"{settings.ollama_base_url}/v1/models", timeout=2.0)
        response.raise_for_status()
        ollama_status = "ok"
    except Exception:
        ollama_status = "error"
    return {"db": db_status, "ollama": ollama_status}
