from typing import Any

from core.api_client import request


def get_health():
    return request("GET", "/health")


def get_providers():
    return request("GET", "/api/providers")


def compare_concepts(message: str):
    return request("POST", "/api/concepts/compare", json={"message": message})


def classify_travel(message: str):
    return request("POST", "/api/travel/classify", json={"message": message})


def create_travel_route_plan(message: str, provider: str | None = None):
    payload = {"message": message}
    if provider:
        payload["provider"] = provider
    return request("POST", "/api/travel/route-plan", json=payload)


def get_travel_cities() -> dict:
    return request("GET", "/api/travel/cities")


def search_travel_places(query: str, size: int = 5) -> dict:
    return request(
        "GET",
        "/api/travel/places/search",
        params={"query": query, "size": size},
    )


def reverse_travel_place(lat: float, lng: float) -> dict:
    return request(
        "GET",
        "/api/travel/places/reverse",
        params={"lat": lat, "lng": lng},
    )


def create_structured_travel_route(
    origin: dict[str, object],
    destination: str,
    start_date: str,
    end_date: str,
    start_time: str,
    end_time: str,
    message: str = "",
    provider: str | None = None,
) -> dict:
    payload: dict[str, Any] = {
        "origin": origin,
        "destination": destination,
        "start_date": start_date,
        "end_date": end_date,
        "start_time": start_time,
        "end_time": end_time,
    }
    if message:
        payload["message"] = message
    if provider:
        payload["provider"] = provider
    return request("POST", "/api/travel/route-plan", json=payload)


def get_transport_tools() -> dict:
    return request("GET", "/api/tools")


def complete_travel_transport(
    message: str,
    origin: dict[str, object],
    destination: dict[str, object],
    departure_time: str | None = None,
    provider: str | None = None,
    tool_choice: str = "auto",
) -> dict:
    payload: dict[str, Any] = {
        "message": message,
        "origin": origin,
        "destination": destination,
        "tool_choice": tool_choice,
    }
    if departure_time:
        payload["departure_time"] = departure_time
    if provider:
        payload["provider"] = provider
    return request("POST", "/api/travel/transport", json=payload)


def generate_response(provider: str, system_prompt: str, message: str):
    return request("POST", "/api/generate", json={"provider": provider, "system_prompt": system_prompt, "message": message})


def compare_providers(providers: list[str], message: str):
    return request("POST", "/api/providers/compare", json={"providers": providers, "message": message})


def preview_prompt(
    role: str,
    instruction: str,
    context: str,
    constraint: str,
    output_format: str = "",
):
    return request(
        "POST",
        "/api/prompts/preview",
        json={
            "role": role,
            "instruction": instruction,
            "context": context,
            "constraint": constraint,
            "output_format": output_format,
        },
    )


def validate_structured_output(schema_type: str, payload: dict[str, Any]):
    return request(
        "POST",
        "/api/structured/validate",
        json={"schema_type": schema_type, "payload": payload},
    )


def generate_structured_output(provider: str, message: str, schema_type: str):
    return request(
        "POST",
        "/api/structured/generate",
        json={"provider": provider, "message": message, "schema_type": schema_type},
    )


def compare_structured_outputs(
    providers: list[str], message: str, schema_type: str = "travel_plan"
):
    return request(
        "POST",
        "/api/structured/compare",
        json={"providers": providers, "message": message, "schema_type": schema_type},
    )
