from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.core.db import get_conn


def lookup_vehicle(plate: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            "select plate, owner_name, vehicle_type from vehicles where plate = %s",
            (plate,),
        ).fetchone()
    if not row:
        return {"plate": plate, "registered": False}
    return {
        "plate": row["plate"],
        "registered": True,
        "owner_name": row["owner_name"],
        "vehicle_type": row["vehicle_type"],
    }


def get_exit_history(plate: str, at: datetime | None = None) -> dict[str, Any]:
    event_at = at or datetime.now(ZoneInfo("Asia/Seoul"))
    if event_at.tzinfo is None:
        event_at = event_at.replace(tzinfo=ZoneInfo("Asia/Seoul"))
    with get_conn() as conn:
        rows = conn.execute(
            """
            select created_at,
                   extract(hour from created_at at time zone 'Asia/Seoul') as hour
            from gate_events
            where plate = %s and direction = 'exit' and decision = 'open'
              and created_at >= %s - interval '30 days' and created_at < %s
            order by created_at desc
            """,
            (plate, event_at, event_at),
        ).fetchall()
    return {
        "plate": plate,
        "count": len(rows),
        "exits": [
            {"at": row["created_at"].isoformat(), "hour_kst": int(row["hour"])}
            for row in rows
        ],
    }


def get_gate_entry(plate: str, at: datetime | None = None) -> dict[str, Any]:
    event_at = at or datetime.now(ZoneInfo("Asia/Seoul"))
    if event_at.tzinfo is None:
        event_at = event_at.replace(tzinfo=ZoneInfo("Asia/Seoul"))
    with get_conn() as conn:
        row = conn.execute(
            """
            select created_at from gate_events
            where plate = %s and direction = 'enter' and decision = 'open'
              and created_at >= %s - interval '24 hours'
              and created_at <= %s
            order by created_at desc limit 1
            """,
            (plate, event_at, event_at),
        ).fetchone()
    return {
        "plate": plate,
        "found": bool(row),
        "entered_at": row["created_at"].isoformat() if row else None,
    }


def request_sobriety_check(plate: str, at: datetime | None = None) -> dict[str, Any]:
    event_at = at or datetime.now(ZoneInfo("Asia/Seoul"))
    if event_at.tzinfo is None:
        event_at = event_at.replace(tzinfo=ZoneInfo("Asia/Seoul"))
    with get_conn() as conn:
        row = conn.execute(
            """
            select id, status, requested_at, resolved_at from sobriety_checks
            where plate = %s
              and requested_at between %s - interval '1 hour' and %s
            order by requested_at desc limit 1
            """,
            (plate, event_at, event_at),
        ).fetchone()
        if not row:
            row = conn.execute(
                "insert into sobriety_checks (plate, requested_at) values (%s, %s) "
                "returning id, status, requested_at, resolved_at",
                (plate, event_at),
            ).fetchone()
    return {
        "check_id": row["id"],
        "plate": plate,
        "status": row["status"],
        "requested_at": row["requested_at"].isoformat(),
        "resolved_at": row["resolved_at"].isoformat() if row["resolved_at"] else None,
    }


def create_alert(
    type: str, plate: str, detail: str, at: datetime | None = None,
) -> dict[str, Any]:
    event_at = at or datetime.now(ZoneInfo("Asia/Seoul"))
    if event_at.tzinfo is None:
        event_at = event_at.replace(tzinfo=ZoneInfo("Asia/Seoul"))
    if type not in {"tailgating", "drunk_suspect"}:
        raise ValueError("type은 tailgating 또는 drunk_suspect여야 합니다.")
    with get_conn() as conn:
        row = conn.execute(
            """
            select id, created_at from alerts
            where alert_type = %s and plate = %s and resolved = false
              and created_at <= %s
            order by created_at desc limit 1
            """,
            (type, plate, event_at),
        ).fetchone()
        created = not row
        if not row:
            row = conn.execute(
                """insert into alerts (alert_type, plate, detail, created_at)
                   values (%s, %s, %s, %s) returning id, created_at""",
                (type, plate, detail, event_at),
            ).fetchone()
    return {
        "alert_id": row["id"], "type": type, "plate": plate,
        "created": created, "created_at": row["created_at"].isoformat(),
    }


OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_vehicle",
            "description": "차량 등록 여부와 소유주 정보를 조회한다.",
            "parameters": {"type": "object", "properties": {
                "plate": {"type": "string"}}, "required": ["plate"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_exit_history",
            "description": "최근 30일 출차 시각 이력을 KST hour와 함께 조회한다.",
            "parameters": {"type": "object", "properties": {
                "plate": {"type": "string"}}, "required": ["plate"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_gate_entry",
            "description": "가장 최근 정상 입차 기록을 조회한다.",
            "parameters": {"type": "object", "properties": {
                "plate": {"type": "string"}}, "required": ["plate"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_sobriety_check",
            "description": "최근 음주측정 상태를 확인하고 필요하면 pending 요청을 만든다.",
            "parameters": {"type": "object", "properties": {
                "plate": {"type": "string"}}, "required": ["plate"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_alert",
            "description": "꼬리물기 또는 음주 의심 경보를 중복 없이 기록한다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["tailgating", "drunk_suspect"]},
                    "plate": {"type": "string"}, "detail": {"type": "string"},
                },
                "required": ["type", "plate", "detail"],
            },
        },
    },
]

TOOL_FUNCTIONS = {
    "lookup_vehicle": lookup_vehicle,
    "get_exit_history": get_exit_history,
    "get_gate_entry": get_gate_entry,
    "request_sobriety_check": request_sobriety_check,
    "create_alert": create_alert,
}
