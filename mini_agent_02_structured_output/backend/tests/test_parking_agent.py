import json
from dataclasses import replace
from datetime import datetime

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.domains.parking_agent import agent_service
from app.domains.parking_agent.schemas import AgentGateDecision, AgentGateRequest
from app.domains.parking_agent.tools import TOOL_FUNCTIONS


def test_mock_transport_executes_tool_and_parses_json(monkeypatch) -> None:
    requests: list[dict] = []
    called: dict = {}

    def fake_history(plate: str, at: datetime | None = None) -> dict:
        called.update({"plate": plate, "at": at})
        return {"plate": plate, "count": 7, "exits": [{"hour_kst": 19}]}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        assert request.url.path == "/v1/chat/completions"
        if len(requests) == 1:
            return httpx.Response(200, json={"choices": [{"message": {
                "role": "assistant", "content": None, "tool_calls": [{
                    "id": "call-1", "type": "function", "function": {
                        "name": "get_exit_history",
                        "arguments": json.dumps({"plate": "잘못된번호"}),
                    },
                }],
            }}]})
        tool_message = body["messages"][-1]
        assert tool_message["role"] == "tool"
        assert "2026-08-25T03:00:00+09:00" in tool_message["content"]
        return httpx.Response(200, json={"choices": [{"message": {
            "role": "assistant",
            "content": '{"decision":"open","reason":"정상 이력","check_id":null}',
        }}]})

    monkeypatch.setitem(TOOL_FUNCTIONS, "get_exit_history", fake_history)
    monkeypatch.setattr(agent_service, "_record_gate", lambda *args: None)
    result = agent_service.run_agent(
        AgentGateRequest(
            plate="12가3456", direction="exit", at=datetime(2026, 8, 25, 3)
        ),
        transport=httpx.MockTransport(handler),
    )
    assert result == AgentGateDecision(decision="open", reason="정상 이력")
    assert called["plate"] == "12가3456"
    assert called["at"].isoformat() == "2026-08-25T03:00:00+09:00"
    assert len(requests) == 2


def test_http_failure_retries_once_then_workflow_fallback(monkeypatch) -> None:
    from app.domains.parking_workflow import service as workflow_service

    calls = 0
    recorded: list[tuple] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"error": "offline"})

    def fallback(plate: str, direction: str, at: datetime) -> dict:
        assert (plate, direction) == ("00테0001", "exit")
        assert at.isoformat() == "2026-08-25T03:00:00+09:00"
        return {
            "decision": "hold", "reason": "룰2: 음주측정 대기",
            "mode": "workflow", "check_id": 17,
        }

    monkeypatch.setattr(workflow_service, "evaluate_gate", fallback)
    monkeypatch.setattr(
        agent_service, "_record_gate",
        lambda payload, decision, at: recorded.append((payload, decision, at)),
    )
    result = agent_service.run_agent(
        AgentGateRequest(
            plate="00테0001", direction="exit", at=datetime(2026, 8, 25, 3)
        ),
        transport=httpx.MockTransport(handler),
    )
    assert calls == 2
    assert result.mode == "agent" and result.check_id == 17
    assert result.reason.startswith("agent 실패 → workflow 폴백: ")
    assert recorded[0][1] == result


def test_ask_returns_answer_and_tool_names(monkeypatch) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json={"choices": [{"message": {
                "role": "assistant", "content": None, "tool_calls": [{
                    "id": "lookup", "type": "function", "function": {
                        "name": "lookup_vehicle", "arguments": '{"plate":"12가3456"}'
                    },
                }],
            }}]})
        return httpx.Response(200, json={"choices": [{"message": {
            "role": "assistant", "content": "등록 차량입니다."
        }}]})

    monkeypatch.setitem(
        TOOL_FUNCTIONS, "lookup_vehicle",
        lambda plate: {"plate": plate, "registered": True},
    )
    monkeypatch.setattr(agent_service, "list_visitors", lambda: [])
    monkeypatch.setattr(agent_service, "list_tailgating", lambda: [])
    result = agent_service.ask_agent(
        "12가3456 등록 차량이야?", httpx.MockTransport(handler)
    )
    assert result == {"answer": "등록 차량입니다.", "tool_calls": ["lookup_vehicle"]}


def test_router_keeps_list_data_and_separate_agent_note(monkeypatch) -> None:
    from app.domains.parking_agent import router

    rows = [{"plate": "11하1111", "entered_at": "now", "spot_id": "A-15"}]
    monkeypatch.setattr(router, "list_visitors", lambda: rows)
    monkeypatch.setattr(router, "agent_note", lambda kind, data: f"{kind} {len(data)}대")
    app = FastAPI()
    app.include_router(router.parking_agent_router)
    response = TestClient(app).get("/parking/agent/visitors")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"] == {"items": rows, "agent_note": "외부인 1대"}


def test_real_endpoint_connection_failure_falls_back_and_records_agent(
    monkeypatch,
) -> None:
    if not agent_service.settings.parking_dsn:
        import pytest

        pytest.skip("PARKING_DSN이 설정된 실DB 통합 실행에서 검증")

    from app.core.db import get_conn
    from app.domains.parking_agent import router

    plate = "00테0001"
    app = FastAPI()
    app.include_router(router.parking_agent_router)
    monkeypatch.setattr(
        agent_service,
        "settings",
        replace(
            agent_service.settings,
            ollama_base_url="http://127.0.0.1:1",
            request_timeout_seconds=0.1,
        ),
    )
    try:
        response = TestClient(app).post(
            "/parking/agent/gate",
            json={"plate": plate, "direction": "enter"},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["decision"] == "open" and data["mode"] == "agent"
        assert data["reason"].startswith("agent 실패 → workflow 폴백: ")
        with get_conn() as conn:
            event = conn.execute(
                """select mode from gate_events where plate = %s
                   order by id desc limit 1""",
                (plate,),
            ).fetchone()
        assert event["mode"] == "agent"
    finally:
        with get_conn() as conn:
            conn.execute("delete from alerts where plate = %s", (plate,))
            conn.execute("delete from sobriety_checks where plate = %s", (plate,))
            conn.execute("delete from spot_events where plate = %s", (plate,))
            conn.execute("delete from gate_events where plate = %s", (plate,))


def test_bad_tool_args_are_fed_back_instead_of_raising(monkeypatch) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        body = json.loads(request.content)
        if calls == 1:  # 소형 모델이 enum 밖 인자를 줌
            return httpx.Response(200, json={"choices": [{"message": {
                "role": "assistant", "content": None, "tool_calls": [{
                    "id": "c1", "type": "function", "function": {
                        "name": "create_alert",
                        "arguments": '{"type":"exit","plate":"12가3456","detail":"x"}',
                    },
                }],
            }}]})
        tool_message = body["messages"][-1]
        assert tool_message["role"] == "tool" and "error" in tool_message["content"]
        return httpx.Response(200, json={"choices": [{"message": {
            "role": "assistant",
            "content": '{"decision":"open","reason":"정상","check_id":null}',
        }}]})

    monkeypatch.setattr(agent_service, "_record_gate", lambda *args: None)
    result = agent_service.run_agent(
        AgentGateRequest(plate="12가3456", direction="exit", at=datetime(2026, 8, 25, 19)),
        transport=httpx.MockTransport(handler),
    )
    assert result.decision == "open" and calls == 2


def test_guard_overrides_open_when_requested_check_is_pending(monkeypatch) -> None:
    from app.domains.parking_agent.schemas import AgentGateDecision as D

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, _sql, _params):
            class R:
                def fetchone(self):
                    return {"status": "pending"}
            return R()

    monkeypatch.setattr(agent_service, "get_conn", lambda: Conn())
    fixed = agent_service._guard_sobriety_consistency(
        D(decision="open", reason="recent_check_pass"), 27
    )
    assert fixed.decision == "hold" and fixed.check_id == 27
    assert "보정" in fixed.reason
    # 측정 요청이 없었으면 손대지 않는다
    assert agent_service._guard_sobriety_consistency(D(decision="open", reason="ok"), None).decision == "open"


def test_normalize_decision_accepts_loose_model_output() -> None:
    n = agent_service._normalize_decision
    assert n({"decision": "OPEN", "reason": "ok"})["decision"] == "open"
    assert n({"decision": " 허용 ", "reason": "ok"})["decision"] == "open"
    assert n({"decision": "Deny (음주)", "reason": {"why": "x"}})["reason"] == '{"why": "x"}'
    assert n({"decision": "hold", "reason": "", "check_id": "17"}) == {
        "decision": "hold", "reason": "(사유 없음)", "check_id": 17,
    }
    import pytest
    with pytest.raises(ValueError):
        n({"decision": "maybe", "reason": "x"})


def test_extract_decision_json_handles_messy_small_model_output() -> None:
    x = agent_service._extract_decision_json
    multi = '{"decision": "open", "reason": "ok"} \n\n만약 \n\n{"decision": "deny", "reason": "x"}'
    assert x(multi)["decision"] == "open"
    assert x('{"name": "open", "parameters": {}}')["decision"] == "open"
    broken = '{"decision":"hold","reason":"대기","check_id":35," plate":12가3456}'
    assert x(broken) == {"decision": "hold", "reason": "대기", "check_id": 35}
    import pytest
    with pytest.raises(ValueError):
        x("그냥 문장")


def test_hold_without_tool_call_creates_check_in_code(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {
            "role": "assistant",
            "content": '{"decision":"hold","reason":"심야 출차","check_id":null}',
        }}]})

    monkeypatch.setattr(agent_service, "_facts_for", lambda plate, when: "- 테스트")
    monkeypatch.setitem(
        TOOL_FUNCTIONS, "request_sobriety_check",
        lambda plate, at=None: {"check_id": 99, "plate": plate, "status": "pending"},
    )
    monkeypatch.setattr(agent_service, "_guard_sobriety_consistency", lambda d, c: d)
    monkeypatch.setattr(agent_service, "_record_gate", lambda *args: None)
    result = agent_service.run_agent(
        AgentGateRequest(plate="00테0001", direction="exit", at=datetime(2026, 8, 25, 3)),
        transport=httpx.MockTransport(handler),
    )
    assert result.decision == "hold" and result.check_id == 99
