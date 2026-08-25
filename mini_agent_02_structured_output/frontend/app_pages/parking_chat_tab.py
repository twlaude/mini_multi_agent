import streamlit as st

from clients.parking_client import answer_text, ask_agent
from core.api_client import BACKEND_URL, BackendAPIError


st.title("💬 주차 관제 챗봇")
st.caption(f"Agent 전용 자연어 질의 · 백엔드: {BACKEND_URL}")

if "parking_chat_messages" not in st.session_state:
    st.session_state.parking_chat_messages = [
        {"role": "assistant", "content": "주차장 상태에 관해 질문해 주세요."}
    ]

for message in st.session_state.parking_chat_messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

question = st.chat_input("예: 지금 외부인 누구 있어?")
if question:
    st.session_state.parking_chat_messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        try:
            with st.spinner("관제 Agent가 확인하고 있습니다..."):
                answer = answer_text(ask_agent(question))
            st.write(answer)
        except BackendAPIError as error:
            answer = f"백엔드 연결 오류: {error}"
            st.error(answer)
    st.session_state.parking_chat_messages.append(
        {"role": "assistant", "content": answer}
    )
