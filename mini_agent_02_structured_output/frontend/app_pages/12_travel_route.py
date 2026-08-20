from __future__ import annotations

from typing import Any

import streamlit as st

from clients.agent_client import create_travel_route_plan
from components.kakao_map import render_kakao_map
from core.api_client import BackendAPIError


RESULT_STATE_KEY = "travel-route-result"
MEAL_ORDER = {"아침": 1, "점심": 2, "저녁": 3}


def _integer(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _text(value: Any, fallback: str = "정보 없음") -> str:
    converted = str(value).strip() if value is not None else ""
    return converted or fallback


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


def _render_result(result: Any) -> None:
    if not isinstance(result, dict) or not isinstance(result.get("plan"), dict):
        st.error("백엔드 응답에 올바른 여행 계획이 없습니다.")
        return

    plan = result["plan"]
    days = min(max(_integer(plan.get("days"), 1), 1), 30)
    nights = max(_integer(plan.get("nights"), max(days - 1, 0)), 0)
    landmarks = _items(plan.get("landmarks"))
    foods = _items(plan.get("foods"))
    places = result.get("places") if isinstance(result.get("places"), list) else []
    raw_not_found = result.get("not_found")
    not_found = []
    if isinstance(raw_not_found, list):
        not_found = list(
            dict.fromkeys(
                _text(item, "") for item in raw_not_found if _text(item, "")
            )
        )

    st.divider()
    st.subheader("여행 계획")
    destination_column, duration_column, place_column = st.columns(3)
    destination_column.metric("목적지", _text(plan.get("destination")))
    duration_column.metric("여행 기간", f"{nights}박 {days}일")
    place_column.metric("추천 장소", f"명소 {len(landmarks)} · 음식 {len(foods)}")
    st.success(_text(plan.get("summary"), "여행 계획이 준비되었습니다."))

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
    st.caption("파란 마커는 랜드마크, 빨간 마커는 음식점입니다. 경로선은 랜드마크만 연결합니다.")
    render_kakao_map(places)


st.title("🗺️ 여행 루트 추천")
st.caption("목적지와 기간을 자연어로 입력하면 일차별 여행 카드와 지도 동선을 만듭니다.")

provider_options = {
    "서버 기본값": None,
    "Mock": "mock",
    "Gemini": "gemini",
    "OpenAI": "openai",
    "Ollama": "ollama",
}

with st.form("travel-route-form"):
    message = st.text_area(
        "여행 요청",
        value="부산에 2박 3일 여행 가고 싶어",
        height=110,
        max_chars=4000,
        help="목적지와 여행 기간, 원하는 분위기나 이동 조건을 함께 적어 주세요.",
    )
    selected_provider = st.selectbox("Provider", list(provider_options))
    submitted = st.form_submit_button("여행 루트 만들기", type="primary")

if submitted:
    normalized_message = message.strip()
    if not normalized_message:
        st.warning("여행 요청을 입력해 주세요.")
    else:
        try:
            with st.spinner(
                "여행 장소와 지도 좌표를 찾고 있어요. 약 10초 정도 걸릴 수 있습니다."
            ):
                response = create_travel_route_plan(
                    normalized_message,
                    provider_options[selected_provider],
                )
            if not isinstance(response, dict) or not isinstance(response.get("plan"), dict):
                st.error("백엔드가 올바른 여행 계획을 반환하지 않았습니다.")
            else:
                st.session_state[RESULT_STATE_KEY] = response
        except BackendAPIError as error:
            st.error(str(error))

if RESULT_STATE_KEY in st.session_state:
    _render_result(st.session_state[RESULT_STATE_KEY])
