import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.core.db import get_conn
from app.main import app


TEST_PLATES = ("00테0001", "00테0002")
client = TestClient(app)


def _cleanup() -> None:
    with get_conn() as conn:
        conn.execute(
            "delete from alerts where plate in (%s, %s)", TEST_PLATES
        )
        conn.execute(
            "delete from sobriety_checks where plate in (%s, %s)", TEST_PLATES
        )
        conn.execute(
            "delete from spot_events where plate in (%s, %s)", TEST_PLATES
        )
        conn.execute(
            "delete from gate_events where plate in (%s, %s)", TEST_PLATES
        )


@pytest.fixture(autouse=True)
def clean_test_rows():
    if not settings.parking_dsn:
        pytest.skip("PARKING_DSN이 필요한 실DB 테스트")
    _cleanup()
    yield
    _cleanup()


def test_spot_event_creates_one_tailgating_alert_and_status_contract() -> None:
    payload = {"spot_id": "A-20", "plate": TEST_PLATES[0], "event": "occupied"}
    first = client.post("/parking/spot-event", json=payload)
    second = client.post("/parking/spot-event", json=payload)

    assert first.status_code == second.status_code == 200
    assert first.json()["data"]["alert_created"] is True
    assert second.json()["data"]["alert_created"] is False
    with get_conn() as conn:
        count = conn.execute(
            """select count(*) as count from alerts
               where plate = %s and alert_type = 'tailgating'""",
            (TEST_PLATES[0],),
        ).fetchone()["count"]
    assert count == 1

    response = client.get("/parking/status")
    body = response.json()
    assert response.status_code == 200
    assert body["success"] is True
    assert len(body["data"]["spots"]) == 20
    assert all("occupied" in spot for spot in body["data"]["spots"])
    assert set(body["data"]) == {
        "spots", "recent_events", "sobriety_checks", "alerts"
    }


def test_sobriety_fail_resolves_check_and_health_is_enveloped(monkeypatch) -> None:
    with get_conn() as conn:
        check_id = conn.execute(
            """insert into sobriety_checks (plate)
               values (%s) returning id""",
            (TEST_PLATES[1],),
        ).fetchone()["id"]

    response = client.post(
        f"/parking/sobriety/{check_id}", json={"result": "fail"}
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "fail"
    with get_conn() as conn:
        check = conn.execute(
            """select resolved_at from sobriety_checks where id = %s""",
            (check_id,),
        ).fetchone()
        alert_count = conn.execute(
            """select count(*) as count from alerts
               where plate = %s and alert_type = 'drunk_suspect'
                 and resolved = false""",
            (TEST_PLATES[1],),
        ).fetchone()["count"]
    assert check["resolved_at"] is not None
    assert alert_count == 1

    class HealthyOllama:
        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(
        "app.domains.parking_common.service.httpx.get",
        lambda *_args, **_kwargs: HealthyOllama(),
    )
    health = client.get("/parking/health")
    assert health.status_code == 200
    assert health.json() == {
        "success": True,
        "message": "주차 서비스 상태를 조회했습니다.",
        "data": {"db": "ok", "ollama": "ok"},
    }
