"""07장의 상태 구분, 승인자와 승인 대상 검증을 확인합니다."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_example(filename: str):
    module_name = f"safety_{filename.removesuffix('.py')}"
    spec = importlib.util.spec_from_file_location(module_name, ROOT / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_empty_place_result_stops_instead_of_repeating(monkeypatch) -> None:
    example = load_example("05_complete_safe_agent.py")
    monkeypatch.setattr(example, "search_places", lambda _city: [])
    state = example.AgentState(run_id="empty-places", owner_id="user-a", city="없는도시")

    result = example.run_until_pause(state)

    assert result["status"] == "blocked"
    assert result["reason"] == "NO_PLACES_FOUND"


def test_changed_approval_target_is_blocked_before_execution() -> None:
    example = load_example("05_complete_safe_agent.py")
    state = example.AgentState(run_id="changed-target", owner_id="user-a", city="제주")
    paused = example.run_until_pause(state)

    result = example.resume_after_approval(
        state,
        {"decision": "approve", "actor": "user-a", "approval_target": {"city": "서울"}},
    )

    assert paused["status"] == "waiting_approval"
    assert result["reason"] == "APPROVAL_TARGET_CHANGED"


def test_rejected_change_is_not_executed() -> None:
    example = load_example("05_complete_safe_agent.py")
    state = example.AgentState(run_id="rejected", owner_id="user-a", city="제주")
    paused = example.run_until_pause(state)

    result = example.resume_after_approval(
        state,
        {"decision": "reject", "actor": "user-a", "approval_target": paused["approval_target"]},
    )

    assert result["status"] == "rejected"
    assert result["reason"] == "USER_REJECTED"


def test_hotel_selection_must_be_from_previous_candidates() -> None:
    example = load_example("07_openai_hotel_selection.py")
    state = example.HotelSelectionState(
        run_id="hotel-selection",
        owner_id="user-a",
        question="부산 호텔을 찾아 줘.",
        status="waiting_user",
        hotel_candidates=[example.HOTELS[0], example.HOTELS[1]],
    )

    valid = example.validate_hotel_selection(state, "user-a", "hotel-busan-001")
    invalid = example.validate_hotel_selection(state, "user-a", "hotel-seoul-001")
    assert valid["valid"] is True
    assert invalid["reason"] == "HOTEL_NOT_IN_CANDIDATES"
