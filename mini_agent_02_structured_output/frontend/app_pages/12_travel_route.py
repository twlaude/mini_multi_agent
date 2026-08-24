from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

import streamlit as st

from clients.agent_client import (
    complete_travel_transport,
    create_structured_travel_route,
    get_travel_cities,
    reverse_travel_place,
    search_travel_places,
)
from components.kakao_map import render_kakao_map
from core.api_client import BackendAPIError

try:
    from streamlit_js_eval import get_geolocation
except ImportError:
    get_geolocation = None


RESULT_STATE_KEY = "travel-route-result"
ORIGIN_STATE_KEY = "travel-origin"
ORIGIN_MODE_STATE_KEY = "travel-origin-active-mode"
CANDIDATES_STATE_KEY = "travel-candidates"
SEARCH_NOTE_STATE_KEY = "travel-search-note"
CITIES_STATE_KEY = "travel-cities"
CONTEXT_STATE_KEY = "travel-context"
TRANSPORT_RESULT_STATE_KEY = "travel-transport-result"
TRANSPORT_QUESTION_STATE_KEY = "travel-transport-question"
MEAL_ORDER = {"아침": 1, "점심": 2, "저녁": 3}
TRACE_LABELS = {
    "tool_selection": "1. Tool 선택",
    "argument_injection": "2. 서버 인자 주입·검증",
    "tool_result": "3. 조회 실행",
    "final_answer": "4. 답변",
}


def _integer(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _text(value: Any, fallback: str = "정보 없음") -> str:
    converted = str(value).strip() if value is not None else ""
    return converted or fallback


def _point(value: Any) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    latitude = _number(value.get("lat"))
    longitude = _number(value.get("lng"))
    if latitude is None or not -90 <= latitude <= 90:
        return None
    if longitude is None or not -180 <= longitude <= 180:
        return None
    return {
        "name": _text(value.get("name"), "이름 없는 장소"),
        "lat": latitude,
        "lng": longitude,
    }


def _load_cities() -> list[dict[str, Any]]:
    cached = st.session_state.get(CITIES_STATE_KEY)
    if isinstance(cached, list):
        return _items(cached)
    try:
        response = get_travel_cities()
    except BackendAPIError as error:
        st.error(str(error))
        return []
    cities = []
    for item in _items(response.get("cities") if isinstance(response, dict) else None):
        point = _point(item)
        if point:
            cities.append(point)
    st.session_state[CITIES_STATE_KEY] = cities
    return cities


def _render_landmark(item: dict[str, Any]) -> None:
    order = max(_integer(item.get("visit_order"), 0), 0)
    title = _text(item.get("name"), "이름 없는 랜드마크")
    with st.container(border=True):
        st.subheader(f"{order}. {title}" if order else title)
        st.caption(_text(item.get("category"), "랜드마크"))
        st.write(_text(item.get("summary")))
        stay_minutes = max(_integer(item.get("stay_minutes"), 0), 0)
        if stay_minutes:
            st.write(f"⏱️ 권장 체류 시간: {stay_minutes}분")
        st.info(f"방문 팁: {_text(item.get('tip'))}")


def _render_food(item: dict[str, Any]) -> None:
    title = _text(item.get("name"), "이름 없는 음식점")
    meal_time = _text(item.get("meal_time"), "식사")
    with st.container(border=True):
        st.subheader(title)
        st.caption(f"{meal_time} · {_text(item.get('cuisine'), '음식 종류 미정')}")
        st.write(f"🍽️ 대표 메뉴: {_text(item.get('signature_menu'))}")
        st.write(f"💳 가격대: {_text(item.get('price_range'))}")
        st.write(f"📍 가까운 명소: {_text(item.get('near_landmark'))}")


def _render_day(
    day: int,
    landmarks: list[dict[str, Any]],
    foods: list[dict[str, Any]],
) -> None:
    daily_landmarks = sorted(
        (item for item in landmarks if _integer(item.get("day")) == day),
        key=lambda item: _integer(item.get("visit_order")),
    )
    daily_foods = sorted(
        (item for item in foods if _integer(item.get("day")) == day),
        key=lambda item: (
            MEAL_ORDER.get(str(item.get("meal_time", "")), 99),
            _text(item.get("name")),
        ),
    )

    landmark_column, food_column = st.columns(2)
    with landmark_column:
        st.markdown("#### 🏛️ 랜드마크")
        if daily_landmarks:
            for item in daily_landmarks:
                _render_landmark(item)
        else:
            st.info("이 일차에 등록된 랜드마크가 없습니다.")

    with food_column:
        st.markdown("#### 🍜 음식")
        if daily_foods:
            for item in daily_foods:
                _render_food(item)
        else:
            st.info("이 일차에 등록된 음식점이 없습니다.")


def _render_transport_result(result: Any) -> None:
    if not isinstance(result, dict):
        return
    final_answer = _text(result.get("final_answer"), "교통편 답변이 없습니다.")
    tool_result = result.get("tool_result")
    tool_succeeded = isinstance(tool_result, dict) and bool(tool_result.get("success"))
    if tool_succeeded:
        st.success(final_answer)
    else:
        st.info(final_answer)
        st.warning("교통 조회 Tool이 실행되지 않았거나 조회에 실패했습니다.")

    with st.expander("Tool 실행 과정"):
        trace = _items(result.get("trace"))
        if not trace:
            st.caption("표시할 Tool trace가 없습니다.")
        for item in trace:
            stage = _text(item.get("stage"), "알 수 없는 단계")
            st.markdown(f"**{TRACE_LABELS.get(stage, stage)}**")
            data = item.get("data")
            if isinstance(data, (dict, list)):
                st.json(data)
            else:
                st.write(data if data is not None else "표시할 내용이 없습니다.")
        st.caption(
            "출발지·도착지 좌표와 출발 시각은 서버가 요청 body에서 강제 주입합니다. "
            "모든 Tool은 조회 전용이며 예약·결제를 수행하지 않습니다."
        )


def _transport_destination(
    places: list[dict[str, Any]], context: dict[str, Any]
) -> dict[str, object] | None:
    landmark = next(
        (item for item in places if item.get("kind") == "landmark"), None
    )
    return _point(landmark) or _point(context.get("destination"))


def _render_transport_section(places: list[dict[str, Any]]) -> None:
    context = st.session_state.get(CONTEXT_STATE_KEY)
    if not isinstance(context, dict) or not _point(context.get("origin")):
        return
    destination = _transport_destination(places, context)
    if not destination:
        return

    st.subheader("교통편 질문")
    st.caption(
        f"조회 목적지: {_text(destination.get('name'))} · "
        "Agent가 조회 전용 Tool을 선택합니다."
    )
    examples = ("KTX로 가면?", "고속버스로 가면?", "차로 가면?")
    for column, example in zip(st.columns(len(examples)), examples):
        if column.button(example, key=f"transport-example-{example}"):
            st.session_state[TRANSPORT_QUESTION_STATE_KEY] = example

    question = st.text_input(
        "교통편 질문",
        placeholder="KTX로 가면?",
        key=TRANSPORT_QUESTION_STATE_KEY,
    )
    if st.button(
        "교통편 알아보기",
        type="primary",
        disabled=not question.strip(),
    ):
        try:
            with st.spinner("교통편 Tool을 선택하고 조회하고 있어요."):
                transport = complete_travel_transport(
                    question.strip(),
                    context["origin"],
                    destination,
                    context.get("departure_time"),
                    context.get("provider"),
                )
            st.session_state[TRANSPORT_RESULT_STATE_KEY] = transport
        except BackendAPIError as error:
            st.error(str(error))

    _render_transport_result(st.session_state.get(TRANSPORT_RESULT_STATE_KEY))


def _render_result(result: Any) -> None:
    if not isinstance(result, dict) or not isinstance(result.get("plan"), dict):
        st.error("백엔드 응답에 올바른 여행 계획이 없습니다.")
        return

    plan = result["plan"]
    schedule = result.get("schedule") if isinstance(result.get("schedule"), dict) else {}
    days = min(
        max(_integer(schedule.get("days"), _integer(plan.get("days"), 1)), 1),
        30,
    )
    nights = max(
        _integer(schedule.get("nights"), _integer(plan.get("nights"), days - 1)),
        0,
    )
    landmarks = _items(plan.get("landmarks"))
    foods = _items(plan.get("foods"))
    places = _items(result.get("places"))
    not_found = []
    raw_not_found = result.get("not_found")
    if isinstance(raw_not_found, list):
        not_found = list(
            dict.fromkeys(
                _text(item, "") for item in raw_not_found if _text(item, "")
            )
        )

    st.divider()
    st.subheader("여행 계획")
    destination_column, duration_column, place_column = st.columns(3)
    destination_column.metric(
        "목적지",
        _text(schedule.get("destination") or plan.get("destination")),
    )
    duration_column.metric("여행 기간", f"{nights}박 {days}일")
    place_column.metric("추천 장소", f"명소 {len(landmarks)} · 음식 {len(foods)}")
    st.success(_text(plan.get("summary"), "여행 계획이 준비되었습니다."))

    if schedule.get("start_time") and schedule.get("end_time"):
        st.caption(
            f"선택 시간: {schedule['start_time']} ~ {schedule['end_time']}"
        )
    provider = _text(result.get("provider"), "서버 기본값")
    model = _text(result.get("model"), "모델 정보 없음")
    latency_ms = max(_integer(result.get("latency_ms"), 0), 0)
    latency_label = f" · {latency_ms / 1000:.1f}초" if latency_ms else ""
    st.caption(f"{provider} · {model}{latency_label}")

    if not_found:
        st.warning(f"지도에서 찾지 못한 장소: {', '.join(not_found)}")

    st.subheader("일차별 일정")
    tabs = st.tabs([f"{day}일차" for day in range(1, days + 1)])
    for day, tab in enumerate(tabs, start=1):
        with tab:
            _render_day(day, landmarks, foods)

    st.subheader("여행 지도")
    st.caption(
        "초록 마커는 출발지, 파란 마커는 랜드마크, 빨간 마커는 음식점입니다. "
        "경로선은 랜드마크만 연결합니다."
    )
    origin_place = result.get("origin") if isinstance(result.get("origin"), dict) else None
    map_places = ([origin_place] if origin_place else []) + places
    render_kakao_map(map_places)
    _render_transport_section(places)


def _initialize_state() -> None:
    defaults = {
        ORIGIN_STATE_KEY: None,
        CANDIDATES_STATE_KEY: [],
        SEARCH_NOTE_STATE_KEY: "",
        TRANSPORT_QUESTION_STATE_KEY: "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _render_origin_block(cities: list[dict[str, Any]]) -> dict[str, object] | None:
    st.subheader("출발지")
    origin_mode = st.radio(
        "출발지 선택",
        ["브라우저 위치", "주소·장소 검색", "도시 선택"],
        horizontal=True,
    )
    previous_mode = st.session_state.get(ORIGIN_MODE_STATE_KEY)
    if previous_mode != origin_mode:
        st.session_state[ORIGIN_MODE_STATE_KEY] = origin_mode
        st.session_state[ORIGIN_STATE_KEY] = None
        st.session_state[CANDIDATES_STATE_KEY] = []
        st.session_state[SEARCH_NOTE_STATE_KEY] = ""

    if origin_mode == "브라우저 위치":
        if get_geolocation is None:
            st.button("📍 현재 위치 가져오기", disabled=True)
            st.warning(
                "브라우저 위치를 사용하려면 streamlit-js-eval 패키지가 필요합니다. "
                "장소 검색이나 도시 선택을 이용해 주세요."
            )
        elif st.button("📍 현재 위치 가져오기"):
            location = get_geolocation()
            coordinates = (location or {}).get("coords") or {}
            latitude = _number(coordinates.get("latitude"))
            longitude = _number(coordinates.get("longitude"))
            if latitude is None or longitude is None:
                st.warning(
                    "위치를 가져오지 못했어요. 장소 검색이나 도시 선택을 이용해 주세요."
                )
            else:
                reverse: dict[str, Any] = {}
                try:
                    reverse = reverse_travel_place(latitude, longitude)
                except BackendAPIError as error:
                    st.warning(str(error))
                name = _text(
                    reverse.get("address"), f"{latitude:.4f},{longitude:.4f}"
                )
                st.session_state[ORIGIN_STATE_KEY] = {
                    "name": name,
                    "lat": latitude,
                    "lng": longitude,
                }
                if reverse.get("note"):
                    st.info(str(reverse["note"]))

    elif origin_mode == "주소·장소 검색":
        query = st.text_input("주소 또는 장소명")
        if st.button("장소 검색"):
            st.session_state[CANDIDATES_STATE_KEY] = []
            st.session_state[SEARCH_NOTE_STATE_KEY] = ""
            if not query.strip():
                st.warning("검색할 주소나 장소명을 입력해 주세요.")
            else:
                try:
                    with st.spinner("출발지 후보를 찾고 있어요."):
                        found = search_travel_places(query.strip(), 5)
                    st.session_state[CANDIDATES_STATE_KEY] = _items(
                        found.get("candidates") if isinstance(found, dict) else None
                    )
                    st.session_state[SEARCH_NOTE_STATE_KEY] = _text(
                        found.get("note") if isinstance(found, dict) else "", ""
                    )
                except BackendAPIError as error:
                    st.error(str(error))

        candidates = _items(st.session_state.get(CANDIDATES_STATE_KEY))
        note = _text(st.session_state.get(SEARCH_NOTE_STATE_KEY), "")
        if note:
            st.info(note)
        if candidates:
            selected_index = st.radio(
                "검색 후보",
                range(len(candidates)),
                format_func=lambda index: (
                    f"{_text(candidates[index].get('name'))} · "
                    f"{_text(candidates[index].get('address'), '주소 없음')} · "
                    f"{_text(candidates[index].get('category'), '카테고리 없음')}"
                ),
            )
            if st.button("이 출발지로 확정"):
                selected_point = _point(candidates[selected_index])
                if selected_point:
                    st.session_state[ORIGIN_STATE_KEY] = selected_point
                else:
                    st.warning("선택한 후보의 좌표가 올바르지 않습니다.")
        elif query.strip() and not note:
            st.caption("검색 버튼을 눌러 출발지 후보를 찾아보세요.")

    elif cities:
        selected_index = st.selectbox(
            "출발 도시",
            range(len(cities)),
            format_func=lambda index: cities[index]["name"],
        )
        st.session_state[ORIGIN_STATE_KEY] = dict(cities[selected_index])
    else:
        st.warning("선택할 수 있는 도시 목록이 없습니다.")

    origin = _point(st.session_state.get(ORIGIN_STATE_KEY))
    if origin:
        st.success(
            f"✅ {origin['name']} ({origin['lat']:.4f}, {origin['lng']:.4f})"
        )
    return origin


_initialize_state()

st.title("🗺️ 여행 루트 추천")
st.caption("출발지와 일정을 고르면 일차별 여행 카드와 지도 동선을 만듭니다.")

cities = _load_cities()
origin = _render_origin_block(cities)

st.subheader("도착지·일정")
destination = None
if cities:
    destination_index = st.selectbox(
        "도착 도시",
        range(len(cities)),
        format_func=lambda index: cities[index]["name"],
    )
    destination = dict(cities[destination_index])
else:
    st.warning("백엔드에서 도시 목록을 불러와야 여행을 만들 수 있습니다.")

today = date.today()
selected_dates = st.date_input(
    "여행 기간",
    value=(today + timedelta(days=1), today + timedelta(days=3)),
)
start_column, end_column = st.columns(2)
with start_column:
    selected_start_time = st.time_input("출발 시간", time(9, 0))
with end_column:
    selected_end_time = st.time_input("종료 시간", time(18, 0))

additional_message = st.text_input(
    "추가 요청 (선택)",
    placeholder="바다와 시장 중심",
)
provider_options = {
    "서버 기본값": None,
    "Mock": "mock",
    "Gemini": "gemini",
    "OpenAI": "openai",
    "Ollama": "ollama",
}
selected_provider = st.selectbox("Provider", list(provider_options))

submitted = st.button(
    "여행 루트 만들기",
    type="primary",
    disabled=not cities,
)
if submitted:
    date_range = (
        tuple(selected_dates)
        if isinstance(selected_dates, (tuple, list))
        else (selected_dates,)
    )
    if not origin:
        st.warning("출발지를 확정해 주세요.")
    elif not destination:
        st.warning("도착 도시를 선택해 주세요.")
    elif len(date_range) != 2:
        st.warning("시작일과 종료일을 모두 선택해 주세요.")
    elif date_range[1] < date_range[0]:
        st.warning("종료일은 시작일보다 빠를 수 없습니다.")
    elif (date_range[1] - date_range[0]).days > 29:
        st.warning("여행 기간은 최대 30일입니다.")
    else:
        provider = provider_options[selected_provider]
        try:
            with st.spinner(
                "여행 장소와 지도 좌표를 찾고 있어요. 약 10초 정도 걸릴 수 있습니다."
            ):
                response = create_structured_travel_route(
                    origin,
                    str(destination["name"]),
                    date_range[0].isoformat(),
                    date_range[1].isoformat(),
                    selected_start_time.isoformat(),
                    selected_end_time.isoformat(),
                    additional_message.strip(),
                    provider,
                )
            if not isinstance(response, dict) or not isinstance(
                response.get("plan"), dict
            ):
                st.error("백엔드가 올바른 여행 계획을 반환하지 않았습니다.")
            else:
                st.session_state[RESULT_STATE_KEY] = response
                st.session_state[CONTEXT_STATE_KEY] = {
                    "origin": origin,
                    "destination": destination,
                    "departure_time": datetime.combine(
                        date_range[0], selected_start_time
                    ).isoformat(),
                    "provider": provider,
                }
                st.session_state.pop(TRANSPORT_RESULT_STATE_KEY, None)
                st.session_state[TRANSPORT_QUESTION_STATE_KEY] = ""
        except BackendAPIError as error:
            st.error(str(error))

if RESULT_STATE_KEY in st.session_state:
    _render_result(st.session_state[RESULT_STATE_KEY])
