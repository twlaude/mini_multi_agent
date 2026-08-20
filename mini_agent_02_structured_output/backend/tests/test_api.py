from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.schemas import TravelImageAnalysis


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["stage"] == "mini_agent_02_structured_output"
    assert response.json()["default_provider"] == "mock"


def test_provider_list_does_not_expose_keys() -> None:
    response = client.get("/api/providers")
    assert response.status_code == 200
    assert [item["provider"] for item in response.json()["providers"]] == [
        "mock", "gemini", "openai", "ollama"
    ]
    assert "api_key" not in response.text.lower()
    assert response.json()["providers"][0]["model"] == "deterministic-structured-mock"


def test_openapi_exposes_generic_structured_route_only() -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/structured/generate" in paths
    assert "/api/structured/travel-plan" not in paths


def test_prompt_preview_keeps_four_sections() -> None:
    response = client.post("/api/prompts/preview", json={
        "role": "여행 도우미", "instruction": "정보 추출", "context": "국내 여행", "constraint": "추측 금지"
    })
    assert response.status_code == 200
    assert all(title in response.json()["prompt"] for title in (
        "[Role]", "[Instruction]", "[Context]", "[Constraint]"
    ))


def test_prompt_preview_adds_optional_output_format() -> None:
    response = client.post("/api/prompts/preview", json={
        "role": "회의 기록자",
        "instruction": "결정 사항 정리",
        "context": "프로젝트 회의",
        "constraint": "추측 금지",
        "output_format": "결정 사항과 할 일 목록",
    })
    assert response.status_code == 200
    assert "[Output Format]" in response.json()["prompt"]


def test_travel_plan_validation_success() -> None:
    response = client.post("/api/structured/validate", json={"payload": {
        "destination": "부산", "summary": "여행", "recommended_days": 2,
        "activities": ["산책"], "cautions": []
    }})
    assert response.status_code == 200
    assert response.json()["valid"] is True


def test_travel_plan_validation_reports_range_and_extra_field() -> None:
    response = client.post("/api/structured/validate", json={"payload": {
        "destination": "부산", "summary": "여행", "recommended_days": 0,
        "activities": [], "cautions": [], "password": "secret"
    }})
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert {item["field"] for item in body["errors"]} >= {"recommended_days", "activities", "password"}


def test_support_ticket_validation_success() -> None:
    response = client.post("/api/structured/validate", json={
        "schema_type": "support_ticket",
        "payload": {
            "category": "billing",
            "priority": "medium",
            "summary": "중복 결제 확인 요청",
            "requires_human": True,
            "missing_information": ["주문 번호"],
        },
    })
    assert response.status_code == 200
    assert response.json()["schema_type"] == "support_ticket"
    assert response.json()["valid"] is True


def test_support_ticket_validation_rejects_literals_and_extra_field() -> None:
    response = client.post("/api/structured/validate", json={
        "schema_type": "support_ticket",
        "payload": {
            "category": "refund",
            "priority": "urgent",
            "summary": "환불 요청",
            "requires_human": True,
            "missing_information": [],
            "password": "secret",
        },
    })
    assert response.status_code == 200
    fields = {item["field"] for item in response.json()["errors"]}
    assert fields >= {"category", "priority", "password"}


def test_mock_structured_output_matches_contract() -> None:
    response = client.post("/api/structured/generate", json={
        "provider": "mock", "message": "제주 2박 3일 여행을 추천해 주세요."
    })
    assert response.status_code == 200
    assert response.json()["content"]["destination"] == "제주"


def test_mock_support_ticket_matches_contract() -> None:
    response = client.post("/api/structured/generate", json={
        "provider": "mock",
        "schema_type": "support_ticket",
        "message": "결제가 두 번 된 것 같습니다.",
    })
    assert response.status_code == 200
    assert response.json()["schema_type"] == "support_ticket"
    assert response.json()["content"]["category"] == "billing"


def test_legacy_travel_plan_route_remains_compatible() -> None:
    response = client.post("/api/structured/travel-plan", json={
        "provider": "mock", "message": "강릉 여행을 추천해 주세요."
    })
    assert response.status_code == 200
    assert response.json()["schema_type"] == "travel_plan"
    assert response.json()["content"]["destination"] == "강릉"


def test_travel_route_mock_returns_geocoded_places(monkeypatch) -> None:
    from app.schemas import GeoPlace

    monkeypatch.setattr(
        "app.routers.structured_router.geocode_plan",
        lambda plan: (
            [GeoPlace(name=plan.landmarks[0].name, kind="landmark", day=1, order=1,
                      lat=35.1, lng=129.0, address="부산 어딘가")],
            [],
        ),
    )
    response = client.post("/api/travel/route-plan", json={
        "provider": "mock", "message": "부산에 2박 3일 여행을 가요."
    })
    assert response.status_code == 200
    body = response.json()
    assert body["plan"]["destination"] == "부산"
    assert (body["plan"]["nights"], body["plan"]["days"]) == (2, 3)
    assert body["plan"]["foods"][0]["meal_time"] in ("아침", "점심", "저녁")
    assert body["places"][0]["kind"] == "landmark"
    assert body["not_found"] == []


def test_travel_route_survives_geocoding_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.kakao_service.geocode_place", lambda *args, **kwargs: None
    )
    response = client.post("/api/travel/route-plan", json={
        "provider": "mock", "message": "서울 여행"
    })
    assert response.status_code == 200
    body = response.json()
    assert body["places"] == []
    assert len(body["not_found"]) == len(body["plan"]["landmarks"]) + len(body["plan"]["foods"])


def test_structured_travel_route_returns_schedule_and_origin(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.structured_router.geocode_plan", lambda _plan: ([], [])
    )
    response = client.post("/api/travel/route-plan", json={
        "provider": "mock",
        "origin": {"name": "서울역", "lat": 37.5547, "lng": 126.9707},
        "destination": "여수",
        "start_date": "2026-08-22",
        "end_date": "2026-08-24",
        "start_time": "09:00",
        "end_time": "18:00",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["plan"]["destination"] == "여수"
    assert (body["schedule"]["nights"], body["schedule"]["days"]) == (2, 3)
    assert body["schedule"]["start_time"] == "09:00:00"
    assert body["origin"] == {
        "name": "서울역", "kind": "origin", "day": 0, "order": 0,
        "lat": 37.5547, "lng": 126.9707, "address": "서울역",
    }


def test_travel_route_requires_message_or_complete_schedule() -> None:
    response = client.post("/api/travel/route-plan", json={"provider": "mock"})
    assert response.status_code == 422
    assert "message 또는 destination" in response.text


def test_place_search_and_reverse_parse_kakao_candidates(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self.payload

    def fake_get(url: str, **_kwargs) -> FakeResponse:
        if url.endswith("keyword.json"):
            return FakeResponse({"documents": [{
                "place_name": "강남역 2호선",
                "road_address_name": "서울 강남구 강남대로 396",
                "address_name": "서울 강남구 역삼동 858",
                "x": "127.0276", "y": "37.4979",
                "category_name": "교통,수송 > 지하철,전철 > 수도권2호선",
            }]})
        return FakeResponse({"documents": [{
            "region_type": "H", "address_name": "서울 중구 회현동",
            "region_1depth_name": "서울특별시",
        }]})

    monkeypatch.setattr(
        "app.services.kakao_service.settings",
        SimpleNamespace(kakao_rest_key="test-key"),
    )
    monkeypatch.setattr("app.services.kakao_service.httpx.get", fake_get)

    search = client.get("/api/travel/places/search", params={"query": "강남역"})
    reverse = client.get(
        "/api/travel/places/reverse", params={"lat": 37.5547, "lng": 126.9707}
    )
    assert search.status_code == reverse.status_code == 200
    assert search.json()["candidates"][0]["name"] == "강남역 2호선"
    assert search.json()["candidates"][0]["lat"] == 37.4979
    assert reverse.json()["address"] == "서울 중구 회현동"
    assert reverse.json()["region"] == "서울특별시"


def test_structured_compare_keeps_provider_errors() -> None:
    response = client.post("/api/structured/compare", json={
        "providers": ["mock", "openai"], "message": "부산 여행"
    })
    assert response.status_code == 200
    results = response.json()["results"]
    assert results[0]["status"] == "success"
    if results[1]["status"] == "error":
        assert "OPENAI_API_KEY" in results[1]["error"]


def test_image_and_tts_routes_are_kept_from_unit_01(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.media_router.analyze_image",
        lambda *_: TravelImageAnalysis(scene_type="other", summary="여행 이미지"),
    )
    monkeypatch.setattr("app.routers.media_router.create_speech", lambda *_: b"mp3")
    image = client.post(
        "/api/media/image-analysis",
        files={"image": ("travel.png", b"fake", "image/png")},
    )
    audio = client.post("/api/media/tts", json={"text": "안내문", "voice": "coral"})
    assert image.status_code == 200
    assert audio.headers["x-synthetic-voice"] == "true"
