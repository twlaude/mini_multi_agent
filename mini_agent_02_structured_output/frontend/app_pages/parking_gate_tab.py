import hashlib
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import streamlit as st

from clients.parking_client import (
    as_items,
    get_parking_status,
    recognize_plate,
    submit_gate,
    submit_sobriety,
    submit_spot_event,
)
from core.api_client import BACKEND_URL, BackendAPIError


st.title("🚧 게이트 시뮬레이터")
st.caption(f"카메라 촬영 또는 직접 입력으로 게이트 시나리오를 확인합니다. · 백엔드: {BACKEND_URL}")

gate_tab, sobriety_tab, sensor_tab = st.tabs(["게이트", "음주측정", "자리 센서"])

with gate_tab:
    if "gate_plate" not in st.session_state:
        st.session_state.gate_plate = "12가3456"

    image = st.camera_input("번호판 촬영", help="촬영한 이미지는 백엔드 OCR로 전송됩니다.")
    if image is not None:
        image_bytes = image.getvalue()
        image_hash = hashlib.sha256(image_bytes).hexdigest()
        if image_hash != st.session_state.get("recognized_plate_image_hash"):
            st.session_state.recognized_plate_image_hash = image_hash
            try:
                with st.spinner("번호판을 인식하고 있습니다..."):
                    recognized = recognize_plate(
                        image.name,
                        image_bytes,
                        image.type or "image/jpeg",
                    )
                plate_value = recognized.get("plate")
                if plate_value:
                    st.session_state.gate_plate = str(plate_value)
                    st.success(f"번호판을 인식했습니다: {plate_value}")
            except BackendAPIError as error:
                st.warning(str(error))

    with st.form("parking-gate-form"):
        plate = st.text_input("차량번호", max_chars=10, key="gate_plate")
        direction_label = st.radio("방향", ["입차", "출차"], horizontal=True)
        use_custom_time = st.checkbox(
            "판단 시각 직접 지정", help="새벽 출차와 같은 데모 시나리오에 사용합니다."
        )
        demo_date = st.date_input(
            "날짜", value=date.today(), disabled=not use_custom_time
        )
        demo_time = st.time_input(
            "출차 시각", value=time(3, 0), disabled=not use_custom_time
        )
        submitted = st.form_submit_button("게이트 판단 요청", use_container_width=True)
    if submitted:
        try:
            at = None
            if use_custom_time:
                at = datetime.combine(
                    demo_date, demo_time, tzinfo=ZoneInfo("Asia/Seoul")
                ).isoformat()
            st.session_state.gate_result = submit_gate(
                plate,
                "enter" if direction_label == "입차" else "exit",
                at,
            )
        except (BackendAPIError, ValueError) as error:
            st.error(str(error))
    result = st.session_state.get("gate_result")
    if isinstance(result, dict):
        decision = str(result.get("decision", "unknown")).lower()
        reason = result.get("reason", "판단 사유가 없습니다.")
        if decision == "open":
            st.success("OPEN · 게이트를 엽니다.")
        elif decision == "hold":
            st.warning("HOLD · 음주측정을 기다립니다.")
        elif decision == "deny":
            st.error("DENY · 출입을 거부합니다.")
        else:
            st.info(f"결과: {decision}")
        st.write(reason)
        if result.get("check_id") is not None:
            st.caption(f"음주측정 ID: {result['check_id']}")

with sobriety_tab:
    if st.button("대기 목록 새로고침"):
        st.rerun()
    try:
        status = get_parking_status()
        checks = as_items(status, "sobriety_checks", "pending_sobriety_checks")
    except BackendAPIError as error:
        checks = []
        st.warning(str(error))
    pending = [item for item in checks if item.get("status", "pending") == "pending"]
    if not pending:
        st.info("대기 중인 음주측정이 없습니다.")
    for item in pending:
        check_id = item.get("id", item.get("check_id"))
        with st.container(border=True):
            columns = st.columns([3, 1, 1])
            columns[0].write(f"{item.get('plate', '번호 미상')} · 측정 ID {check_id}")
            if columns[1].button("통과", key=f"pass-{check_id}", disabled=check_id is None):
                try:
                    submit_sobriety(int(check_id), "pass")
                    st.success("통과로 처리했습니다.")
                    st.rerun()
                except (BackendAPIError, ValueError) as error:
                    st.error(str(error))
            if columns[2].button("불합격", key=f"fail-{check_id}", disabled=check_id is None):
                try:
                    submit_sobriety(int(check_id), "fail")
                    st.error("불합격으로 처리했습니다.")
                    st.rerun()
                except (BackendAPIError, ValueError) as error:
                    st.error(str(error))

with sensor_tab:
    with st.form("parking-spot-event-form"):
        spot_id = st.selectbox("주차면", [f"A-{number:02d}" for number in range(1, 21)])
        sensor_plate = st.text_input("감지 차량번호", value="99허9999", max_chars=10)
        event_label = st.radio("센서 이벤트", ["점유", "해제"], horizontal=True)
        sensor_submitted = st.form_submit_button("자리 센서 이벤트 전송", use_container_width=True)
    if sensor_submitted:
        try:
            submit_spot_event(
                spot_id, sensor_plate, "occupied" if event_label == "점유" else "vacated"
            )
            st.success("자리 센서 이벤트를 전송했습니다.")
        except (BackendAPIError, ValueError) as error:
            st.error(str(error))
