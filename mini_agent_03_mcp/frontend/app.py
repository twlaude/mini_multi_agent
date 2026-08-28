import os

import httpx
import streamlit as st


BASE_URL = os.getenv("BACKEND_API_URL", "http://127.0.0.1:8000").rstrip("/")


def get(path: str, params: dict | None = None) -> dict:
    response = httpx.get(f"{BASE_URL}{path}", params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def post(path: str, payload: dict) -> dict:
    response = httpx.post(f"{BASE_URL}{path}", json=payload, timeout=120)
    response.raise_for_status()
    return response.json()


st.set_page_config(page_title="Mini Agent 03 MCP", page_icon="🔌", layout="wide")
st.title("Mini Agent 03 · MCP")
st.caption(
    "FastAPI가 5팀 MCP Server 3개(숙소·관광지·날씨)의 Tool을 발견하고 "
    "순차 Agent Loop로 호출합니다."
)

try:
    status = get("/api/mcp/status")
    st.success(f"MCP 연결: {status['status']} · Tool {status['tool_count']}개")
    for server in status["servers"]:
        st.write(
            f"- `{server['name']}` · {server['transport']} · "
            f"{server['endpoint']}"
        )
except httpx.HTTPError:
    st.warning(
        "MCP Server에 연결할 수 없습니다. hotel(8030)·tour_spot(8040)·"
        "weather(8050) 서버가 모두 실행 중인지 확인하세요."
    )

if st.button("MCP Tool 발견"):
    try:
        st.json(get("/api/mcp/tools"))
    except httpx.HTTPError as error:
        st.error(f"Backend 호출 실패: {error}")

question = st.text_input(
    "질문",
    "서울 현재 날씨 알려주고, 부산 관광지 3곳이랑 부산 호텔 중 15만원 이하 3곳 추천해줘.",
)
if st.button("MCP Agent 실행", type="primary"):
    try:
        result = post("/api/mcp/run", {"question": question})
        st.success(result["answer"])
        left, right = st.columns(2)
        left.metric("GPT 호출 횟수", result["llm_calls"])
        right.metric("실행된 Tool 수", len(result["trace"]))
        st.subheader("GPT가 선택하고 MCP가 실행한 Tool")
        for index, item in enumerate(result["trace"], start=1):
            title = (
                f"Round {item['round']} · {item['server']} · "
                f"{item['tool']}"
            )
            with st.expander(title, expanded=True):
                st.caption(f"Public Tool: {item['public_tool']}")
                st.write("Arguments")
                st.json(item["arguments"])
                st.write("Tool Result")
                st.code(item["result"])
                if item["is_error"]:
                    st.error("MCP Tool 실행 오류")
        with st.expander("전체 응답 JSON"):
            st.json(result)
    except httpx.HTTPError as error:
        st.error(f"Backend 호출 실패: {error}")

with st.expander("MCP Resource 확인"):
    if st.button("Resource 목록"):
        try:
            st.json(get("/api/mcp/resources"))
        except httpx.HTTPError as error:
            st.error(f"Backend 호출 실패: {error}")
    if st.button("오늘 날짜 읽기 (hotel · yeogi://today)"):
        try:
            st.json(get("/api/mcp/resource", {"server": "hotel", "uri": "yeogi://today"}))
        except httpx.HTTPError as error:
            st.error(f"Backend 호출 실패: {error}")
