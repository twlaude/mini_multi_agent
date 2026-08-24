import streamlit as st


st.set_page_config(page_title="주차 출입 시스템", page_icon="🅿️", layout="wide")

dashboard_page = st.Page("app_pages/01_dashboard.py", title="관제 대시보드", default=True)
gate_page = st.Page("app_pages/02_gate_simulator.py", title="게이트 시뮬레이터")
chat_page = st.Page("app_pages/03_chatbot.py", title="관제 챗봇 (Agent)")

navigation = st.navigation([dashboard_page, gate_page, chat_page], position="hidden")

with st.sidebar:
    st.title("🅿️ 주차 출입 시스템")
    st.caption("mini_agent_02 · 워크플로우 vs AI Agent")
    st.page_link(dashboard_page, label="📊 관제 대시보드")
    st.page_link(gate_page, label="🚧 게이트 시뮬레이터")
    st.page_link(chat_page, label="💬 관제 챗봇 (Agent)")

navigation.run()
