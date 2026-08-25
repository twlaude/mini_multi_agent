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
        if message.get("tool_calls"):
            st.caption("사용 도구: " + ", ".join(message["tool_calls"]))

question = st.chat_input("예: 지금 외부인 누구 있어?")
if question:
    st.session_state.parking_chat_messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        try:
            with st.spinner("관제 Agent가 확인하고 있습니다..."):
                result = ask_agent(question)
                answer = answer_text(result)
                tool_calls = result.get("tool_calls", []) if isinstance(result, dict) else []
            st.write(answer)
            if tool_calls:
                st.caption("사용 도구: " + ", ".join(tool_calls))
        except BackendAPIError as error:
            answer = f"백엔드 연결 오류: {error}"
            tool_calls = []
            st.error(answer)
    st.session_state.parking_chat_messages.append(
        {"role": "assistant", "content": answer, "tool_calls": tool_calls}
    )
