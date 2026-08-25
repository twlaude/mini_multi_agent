import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.core.db import get_conn
from app.domains.parking_workflow.schemas import GateRequest
from app.domains.parking_workflow.service import evaluate_gate
from app.main import app


pytestmark = pytest.mark.skipif(
    not os.getenv("PARKING_DSN"), reason="PARKING_DSN 실DB가 필요합니다."
)
client = TestClient(app)
KST = ZoneInfo("Asia/Seoul")
TOUCHED_PLATES = ("12가3456", "34나5678", "45사3456", "99허9999")


@pytest.fixture(autouse=True)
def cleanup_created_rows():
    with get_conn() as conn:
        baselines = {
            table: conn.execute(f"select coalesce(max(id), 0) as id from {table}").fetchone()[
                "id"
            ]
            for table in (
                "gate_events",
                "sobriety_checks",
                "alerts",
            )
        }
    yield
    with get_conn() as conn:
        for table in ("alerts", "sobriety_checks", "gate_events"):
            conn.execute(
                f"delete from {table} where id > %s and plate = any(%s)",
                (baselines[table], list(TOUCHED_PLATES)),
            )


def _today(hour: int, minute: int = 0) -> datetime:
    return datetime.now(KST).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )


def _gate(plate: str, at: datetime) -> dict:
    response = client.post(
        "/parking/workflow/gate",
        json={"plate": plate, "direction": "exit", "at": at.isoformat()},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"success", "message", "data"}
    assert body["success"] is True
    return body["data"]


def test_exit_rules_hold_pass_deny_and_normal_time() -> None:
    early = _today(3)
    held = _gate("12가3456", early)
    assert held["decision"] == "hold"
    assert held["check_id"]
    assert "현재 03시" in held["reason"]

    passed = client.post(
        f"/parking/sobriety/{held['check_id']}", json={"result": "pass"}
    )
    assert passed.status_code == 200, passed.text
    assert _gate("12가3456", early)["decision"] == "open"

    failed_hold = _gate("34나5678", early)
    failed = client.post(
        f"/parking/sobriety/{failed_hold['check_id']}", json={"result": "fail"}
    )
    assert failed.status_code == 200, failed.text
    denied = _gate("34나5678", early)
    assert denied["decision"] == "deny"
    with get_conn() as conn:
        alert = conn.execute(
            """select 1 from alerts where plate = '34나5678'
               and alert_type = 'drunk_suspect' and resolved = false"""
        ).fetchone()
    assert alert is not None

    normal = _gate("12가3456", _today(19, 10))
    assert normal["decision"] == "open"
    assert "평소 출차 시간대" in normal["reason"]


def test_seed_visitors_and_tailgating_are_returned() -> None:
    visitors = client.get("/parking/workflow/visitors")
    tailgating = client.get("/parking/workflow/tailgating")
    assert visitors.status_code == tailgating.status_code == 200
    assert {item["plate"] for item in visitors.json()["data"]} >= {
        "11하1111",
        "22호2222",
    }
    suspicious = {item["plate"]: item for item in tailgating.json()["data"]}
    assert "99허9999" in suspicious  # 자리는 데모 중 옮겨질 수 있어 plate만 확인


def test_evaluate_gate_skips_sparse_history_without_recording_event() -> None:
    with get_conn() as conn:
        before = conn.execute(
            "select count(*) as count from gate_events where plate = '45사3456'"
        ).fetchone()["count"]
    result = evaluate_gate("45사3456", "exit", _today(3))
    with get_conn() as conn:
        after = conn.execute(
            "select count(*) as count from gate_events where plate = '45사3456'"
        ).fetchone()["count"]
    assert result["decision"] == "open"
    assert "5건 미만" in result["reason"]
    assert after == before


def test_process_gate_always_records_workflow_mode() -> None:
    payload = GateRequest(plate="45사3456", direction="exit", at=_today(3))
    response = client.post(
        "/parking/workflow/gate", json=payload.model_dump(mode="json")
    )
    assert response.status_code == 200
    with get_conn() as conn:
        event = conn.execute(
            """select mode, created_at from gate_events
               where plate = '45사3456' order by id desc limit 1"""
        ).fetchone()
    assert event["mode"] == "workflow"
    assert event["created_at"].astimezone(KST).hour == 3
