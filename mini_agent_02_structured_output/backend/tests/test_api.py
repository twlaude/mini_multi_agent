from datetime import datetime
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


def test_odsay_normalizes_ktx_and_srt(monkeypatch) -> None:
    from app.schemas import TransitRouteArgs
    from app.services.odsay_service import search_transit_routes

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            def path(start: str, minutes: int, fare: int) -> dict:
                return {
                    "pathType": 11,
                    "info": {
                        "totalTime": minutes, "totalPayment": fare,
                        "firstStartStation": start, "lastEndStation": "부산역",
                    },
                    "subPath": [{
                        "trafficType": 4, "trainType": 1, "startName": start,
                        "trainSpSeatPayment": fare + 20000,
                        "intervalTime": 30, "intervalCount": 20,
                    }],
                }

            return {"result": {"path": [
                path("서울역", 138, 59800), path("수서", 145, 52600)
            ]}}

    def fake_get(url: str, **kwargs) -> FakeResponse:
        assert url.endswith("searchPubTransPathT")
        assert kwargs["headers"]["Referer"] == "http://localhost"
        assert kwargs["params"]["SearchType"] == 1
        return FakeResponse()

    monkeypatch.setattr(
        "app.services.odsay_service.settings", SimpleNamespace(odsay_key="test-key")
    )
    monkeypatch.setattr("app.services.odsay_service.httpx.get", fake_get)
    result = search_transit_routes(TransitRouteArgs(
        origin_lat=37.5547, origin_lng=126.9707,
        dest_lat=35.1631, dest_lng=129.1635, mode="train",
    ))
    assert [option["label"] for option in result["options"]] == ["KTX", "SRT"]
    assert result["options"][0]["fare_krw"] == 59800
    assert result["options"][0]["premium_fare_krw"] == 79800


def test_kakao_mobility_normalizes_costs(monkeypatch) -> None:
    from app.schemas import DrivingRouteArgs
    from app.services.kakao_mobility_service import search_driving_route

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"routes": [{
                "result_code": 0,
                "summary": {
                    "distance": 408000, "duration": 18420,
                    "fare": {"toll": 22000, "taxi": 420000},
                },
            }]}

    def fake_get(url: str, **kwargs) -> FakeResponse:
        assert url.endswith("/future/directions")
        assert kwargs["params"]["departure_time"] == "202608220900"
        assert kwargs["headers"]["Authorization"] == "KakaoAK test-key"
        return FakeResponse()

    monkeypatch.setattr(
        "app.services.kakao_mobility_service.settings",
        SimpleNamespace(kakao_rest_key="test-key"),
    )
    monkeypatch.setattr("app.services.kakao_mobility_service.httpx.get", fake_get)
    result = search_driving_route(DrivingRouteArgs(
        origin_lat=37.5547, origin_lng=126.9707,
        dest_lat=35.1631, dest_lng=129.1635,
        departure_time=datetime(2026, 8, 22, 9, 0),
    ))
    assert (result["distance_km"], result["minutes"]) == (408.0, 307)
    assert (result["toll_krw"], result["fuel_krw"], result["total_krw"]) == (
        22000, 56100, 78100
    )


def test_tool_run_rejects_unknown_tool() -> None:
    response = client.post("/api/tools/run", json={
        "tool_name": "book_train_ticket", "arguments": {}
    })
    assert response.status_code == 200
    assert response.json()["error"]["code"] == "TOOL_NOT_ALLOWED"


def test_tool_run_reports_argument_validation() -> None:
    response = client.post("/api/tools/run", json={
        "tool_name": "get_transit_route", "arguments": {"mode": "train"}
    })
    assert response.status_code == 200
    assert response.json()["error"]["code"] == "TOOL_VALIDATION_ERROR"
    assert {item["field"] for item in response.json()["error"]["details"]} >= {
        "origin_lat", "origin_lng", "dest_lat", "dest_lng"
    }


def test_transport_mock_selects_tool_and_overwrites_coordinates(monkeypatch) -> None:
    from app.providers import select_tool_mock

    calls: list[tuple[str, dict]] = []

    def fake_select(_provider: str, message: str, tool_choice: str):
        decision = select_tool_mock(message, tool_choice)
        decision.arguments.update({
            "origin_lat": 0, "origin_lng": 0, "dest_lat": 0, "dest_lng": 0,
            "departure_time": "2000-01-01T00:00:00",
        })
        return decision

    def fake_run(name: str, arguments: dict) -> dict:
        calls.append((name, dict(arguments)))
        if name == "get_driving_route":
            return {
                "distance_km": 408.0, "minutes": 307, "toll_krw": 22000,
                "fuel_krw": 56100, "total_krw": 78100,
            }
        return {"options": [{
            "label": "KTX", "from": "서울역", "to": "부산역",
            "minutes": 138, "fare_krw": 59800,
        }]}

    monkeypatch.setattr("app.routers.transport_router.select_tool", fake_select)
    monkeypatch.setattr("app.routers.transport_router.run_tool", fake_run)
    base = {
        "provider": "mock",
        "origin": {"name": "서울역", "lat": 37.5547, "lng": 126.9707},
        "destination": {"name": "해운대", "lat": 35.1631, "lng": 129.1635},
    }
    driving = client.post("/api/travel/transport", json={
        **base, "message": "차로 가면?", "departure_time": "2026-08-22T09:00:00"
    })
    transit = client.post("/api/travel/transport", json={
        **base, "message": "KTX로 가면?"
    })
    assert driving.status_code == transit.status_code == 200
    assert [call[0] for call in calls] == ["get_driving_route", "get_transit_route"]
    assert calls[0][1]["origin_lat"] == 37.5547
    assert calls[0][1]["dest_lng"] == 129.1635
    assert calls[0][1]["departure_time"] == "2026-08-22T09:00:00"
    assert calls[1][1]["mode"] == "train"
    assert "departure_time" not in calls[1][1]
    assert "합계 78,100원" in driving.json()["final_answer"]
    assert "KTX 서울역→부산역 2시간 18분 59,800원" in transit.json()["final_answer"]


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
