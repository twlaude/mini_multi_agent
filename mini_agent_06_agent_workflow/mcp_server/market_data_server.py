"""Stock Portfolio Agent가 사용하는 시장 데이터 Streamable HTTP MCP Server입니다.

business_tools_server와는 별개의 프로세스이며 다른 포트에서 실행됩니다.
Backend는 Agent Profile의 mcp_server 값에 따라 어느 Server에 연결할지 결정합니다.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")
MCP_HOST = os.getenv("MARKET_MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MARKET_MCP_PORT", "8011"))

mcp = FastMCP(
    "mini-agent-06-market-data",
    instructions="주식 포트폴리오 Agent가 사용하는 교육용 시장 데이터 Server입니다. 실제 시세가 아닙니다.",
    host=MCP_HOST,
    port=MCP_PORT,
    stateless_http=True,
    json_response=True,
)

STOCKS = {
    "005930": {"name": "삼성전자", "price": 71_200, "change_pct": -0.8, "market_status": "open"},
    "000660": {"name": "SK하이닉스", "price": 182_500, "change_pct": 2.1, "market_status": "open"},
    "035420": {"name": "NAVER", "price": 168_000, "change_pct": 0.3, "market_status": "open"},
    "005380": {"name": "현대차", "price": 245_000, "change_pct": -1.2, "market_status": "halted"},
}
HOLDINGS = {
    "student-01": [
        {"code": "005930", "quantity": 10, "avg_price": 68_000},
        {"code": "000660", "quantity": 3, "avg_price": 195_000},
    ],
    "student-02": [],
}


@mcp.tool()
def search_stock(query: str) -> dict:
    """종목명 또는 종목 코드로 종목을 검색합니다."""
    normalized = query.strip().lower()
    if not normalized:
        return {"success": False, "query": query, "error": "INVALID_QUERY", "items": []}
    items = [
        {"code": code, "name": data["name"]}
        for code, data in STOCKS.items()
        if normalized in data["name"].lower() or normalized == code
    ]
    return {"success": True, "query": query, "items": items}


@mcp.tool()
def get_quote(code: str) -> dict:
    """종목 코드로 현재가, 등락률과 거래 상태를 조회합니다."""
    code = code.strip()
    data = STOCKS.get(code)
    if data is None:
        return {"success": False, "code": code, "error": "STOCK_NOT_FOUND"}
    return {"success": True, "code": code, **data}


@mcp.tool()
def get_holdings(user_id: str) -> dict:
    """사용자 ID로 보유 종목, 수량과 평균 매수 단가를 조회합니다."""
    user_id = user_id.strip()
    items = HOLDINGS.get(user_id)
    if items is None:
        return {"success": False, "user_id": user_id, "error": "USER_NOT_FOUND", "items": []}
    return {"success": True, "user_id": user_id, "items": items}


@mcp.tool()
def calculate_pnl(code: str, quantity: int, avg_price: int) -> dict:
    """종목 코드, 수량, 평균 매수 단가로 현재가 기준 평가 손익을 계산합니다. 주문을 내지 않습니다."""
    code = code.strip()
    if quantity < 1:
        raise ValueError("quantity는 1 이상이어야 합니다.")
    if avg_price < 1:
        raise ValueError("avg_price는 1 이상이어야 합니다.")
    data = STOCKS.get(code)
    if data is None:
        return {"success": False, "code": code, "error": "STOCK_NOT_FOUND"}
    current_price = data["price"]
    pnl = (current_price - avg_price) * quantity
    return {
        "success": True,
        "code": code,
        "name": data["name"],
        "quantity": quantity,
        "avg_price": avg_price,
        "current_price": current_price,
        "market_value": current_price * quantity,
        "pnl": pnl,
        "pnl_pct": round((current_price - avg_price) / avg_price * 100, 2),
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
