import streamlit as st

from clients.parking_client import (
    as_items,
    get_parking_status,
    get_tailgating,
    get_visitors,
)
from core.api_client import BACKEND_URL, BackendAPIError


st.title("📊 주차 관제 대시보드")
st.caption(f"백엔드: {BACKEND_URL} · 상태는 5초마다 갱신됩니다.")


def _render_spots(spots: list[dict]) -> None:
    by_id = {str(item.get("spot_id")): item for item in spots}
    for row_start in range(1, 21, 5):
        columns = st.columns(5)
        for offset, column in enumerate(columns):
            spot_id = f"A-{row_start + offset:02d}"
            spot = by_id.get(spot_id, {"spot_id": spot_id, "occupied": False})
            plate = spot.get("plate") or "빈자리"
            occupied = bool(spot.get("occupied") or spot.get("plate"))
            with column.container(border=True):
                st.markdown(f"**{'🔴' if occupied else '🟢'} {spot_id}**")
                st.write(plate)


@st.fragment(run_every=5.0)
def status_panel() -> None:
    try:
        status = get_parking_status()
    except BackendAPIError as error:
        st.warning(f"상태를 불러오지 못했습니다: {error}")
        _render_spots([])
        return

    spots = as_items(status, "spots", "parking_spots")
    events = as_items(status, "recent_gate_events", "gate_events", "recent_events")
    alerts = as_items(status, "alerts", "unresolved_alerts")
    checks = as_items(status, "sobriety_checks", "pending_sobriety_checks")
    occupied = sum(bool(item.get("occupied") or item.get("plate")) for item in spots)

    metrics = st.columns(4)
    metrics[0].metric("전체 주차면", 20)
    metrics[1].metric("점유", occupied)
    metrics[2].metric("미해결 경보", len(alerts))
    metrics[3].metric("음주측정 대기", len(checks))

    st.subheader("주차면 현황")
    _render_spots(spots)
    left, right = st.columns(2)
    with left:
        st.subheader("최근 게이트 이벤트")
        st.dataframe(events, use_container_width=True, hide_index=True)
    with right:
        st.subheader("미해결 경보")
        if alerts:
            st.error(f"미해결 경보 {len(alerts)}건")
        st.dataframe(alerts, use_container_width=True, hide_index=True)


status_panel()

st.divider()
st.subheader("Agent 차량 점검")
st.caption("Ollama 장애 시 백엔드가 자동으로 workflow 규칙으로 폴백합니다.")
left, right = st.columns(2)
with left:
    if st.button("외부인 차량 조회", use_container_width=True):
        try:
            st.session_state.parking_visitors = get_visitors()
        except BackendAPIError as error:
            st.error(str(error))
    if "parking_visitors" in st.session_state:
        visitors = st.session_state.parking_visitors
        if isinstance(visitors, dict) and visitors.get("agent_note"):
            st.info(visitors["agent_note"])
        st.dataframe(
            as_items(visitors, "items"),
            use_container_width=True,
            hide_index=True,
        )
with right:
    if st.button("꼬리물기 점검", use_container_width=True):
        try:
            st.session_state.parking_tailgating = get_tailgating()
        except BackendAPIError as error:
            st.error(str(error))
    if "parking_tailgating" in st.session_state:
        tailgating = st.session_state.parking_tailgating
        if isinstance(tailgating, dict) and tailgating.get("agent_note"):
            st.info(tailgating["agent_note"])
        st.dataframe(
            as_items(tailgating, "items"),
            use_container_width=True,
            hide_index=True,
        )
